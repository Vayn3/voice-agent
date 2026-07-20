import argparse
import asyncio
import audioop
import gzip
import inspect
import json
import os
import queue
import signal
import struct
import time
import uuid
from typing import Any, Dict, List, Optional

import pyaudio
import websockets

# 复用参考系统的模块（逐字复制而来），保证与下位机接收端字节级一致
from audio_constants import (
    ACTION_INDEX_BY_KEYWORD,
    ASR_KWS_PATTERNS,
    KWS_PRIORITY,
    LLM_KWS_PATTERNS,
    REPEAT_ACTION_COUNT,
    TARGET_CHANNELS,
    TARGET_CHUNK_SAMPLES,
    TARGET_SAMPLE_RATE,
    TARGET_SAMPLE_WIDTH,
)
from ros_audio import Ros1SpeakerStream

# ROS1 运行期依赖（Windows 开发机通常无 rospy，用 try/except 优雅降级）
try:
    import rospy
    from std_msgs.msg import Bool, Int32

    _HAS_ROS1 = True
except Exception:
    rospy = None
    Bool = None
    Int32 = None
    _HAS_ROS1 = False


# =========================
# 你通常只需要修改这个配置区
# =========================

# 从环境变量读取火山控制台创建的 API Key，避免把密钥写入源码。
API_KEY = os.getenv("VOLC_REALTIME_API_KEY", "")
MODEL_VERSION = os.getenv("VOLC_REALTIME_MODEL_VERSION", "1.2.1.1")

# 固定服务配置。一般不要改。
BASE_URL = "wss://openspeech.bytedance.com/api/v3/realtime/dialogue"
RESOURCE_ID = "volc.speech.dialog"

# 发音人。可按 README 替换为其他 speaker。
SPEAKER = "zh_male_xiaotian_jupiter_bigtts"

# 系统级设定：这里写角色、任务、回答边界、开场要求。
SYSTEM_PROMPT = (
    "你现在是课程报告智能助教，正在对学生进行一对一语音问答。"
    "开场白先介绍一下目前在干什么，然后引入问题"
    "请依次提问以下六个问题：首先询问他们为何选择价格和辣度作为启动问题；接着问实际点击率低于预期的原因；然后探讨麻辣烫被替换后的表现变化说明了什么；再了解初始权重是如何设定的；随后让其详细解释FinalScore的计算过程；最后引导他们反思本项目如何体现对推荐系统尤其是冷启动问题的理解。每个问题最多追问两次，若回答包含充分标准中的要点即可进入下一题。当所有高优先级问题完成后，可宣布问答结束。禁止询问与报告无关的个人信息或超出课程范围的技术细节。"
)

# 音频配置。
# - 上行：麦克风采集后统一重采样到 16k / 单声道 / 16-bit PCM 再发给大模型。
# - 下行：服务端 TTS 输出 24k / 单声道 / Float32 PCM（火山 "pcm" 实为 float32，前端
#   VoiceQAConsole 用 Float32Array 播放即证明）。ROS(audio_common_msgs/AudioData 为
#   int16[]) 与本地 PyAudio(paInt16) 播放链路均按 int16(s16le) 处理，故写入前需先把
#   Float32 转成 int16，否则机器人/扬声器会播放出电音或静音。
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK = 3200  # 本地 PyAudio 播放缓冲；ROS 发布模式下不影响


def float32_pcm_to_int16(float_bytes: bytes) -> bytes:
    """火山引擎实时对话下行 TTS 实际为 Float32 PCM（4 字节/采样，范围 [-1,1]），
    但 ROS(audio_common_msgs/AudioData 为 int16[]) 与本地 PyAudio(paInt16) 均按
    int16(s16le) 处理。这里把 4 字节 float 转成 2 字节 int16，避免机器人/扬声器
    播放出电音或静音。"""
    if not float_bytes or len(float_bytes) % 4 != 0:
        return float_bytes  # 非 4 字节对齐，原样兜底
    n = len(float_bytes) // 4
    floats = struct.unpack("<%df" % n, float_bytes[: n * 4])
    return b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, x)) * 32767)) for x in floats
    )

# 服务端静默等待时间，范围通常是 [10, 120]。
RECV_TIMEOUT = 120


def _env_opt_int(name: str) -> Optional[int]:
    val = os.getenv(name, "").strip()
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        return None


# =========================
# ROS / 麦克风 相关配置（与参考系统 config.py 对齐；均可用环境变量覆盖）
# =========================

# 输出模式：ros1=把大模型音频发布到 ROS 话题（默认，机器人上使用）；pyaudio=本地扬声器播放（Windows 调试）。
OUTPUT_AUDIO_MODE = os.getenv("OUTPUT_AUDIO_MODE", "ros1")
# 下行音频发布话题、发布节点名、队列、控制话题（停止播放）。接收端据此订阅，务必与下位机一致。
ROS_AUDIO_TOPIC = os.getenv("ROS_AUDIO_TOPIC", "/audio")
ROS_AUDIO_NODE_NAME = os.getenv("ROS_AUDIO_NODE_NAME", "speaker_publisher")
ROS_AUDIO_QUEUE_SIZE = int(os.getenv("ROS_AUDIO_QUEUE_SIZE", "10"))
ROS_AUDIO_CONTROL_TOPIC = os.getenv("ROS_AUDIO_CONTROL_TOPIC", "/audio/control")
# 关键词命中后发布动作 index 的话题（std_msgs/Int32）。
ACTION_INDEX_TOPIC = os.getenv("ACTION_INDEX_TOPIC", "/action_index")
# 下位机播放状态反馈话题（std_msgs/Bool），订阅用于（后续全双工）判断远端是否在播放。
REMOTE_STATUS_TOPIC = os.getenv("REMOTE_STATUS_TOPIC", "/audio_playing_status")

# 麦克风设备选择（Ubuntu 友好）：
# - 均不填 → 使用系统默认输入设备（PulseAudio/PortAudio 默认，随系统设置变化）。
# - MIC_DEVICE_NAME → 不区分大小写子串模糊匹配（如 "USB"/"pulse"），优先级高于索引。
# - MIC_DEVICE_INDEX → 明确指定 PyAudio 设备索引（用 --list-devices 查看）。
# - MIC_SAMPLE_RATE → 打开麦克风的采样率；留空则用所选设备的默认采样率，之后统一重采样到 16k。
MIC_DEVICE_NAME = os.getenv("MIC_DEVICE_NAME", "").strip() or None
MIC_DEVICE_INDEX = _env_opt_int("MIC_DEVICE_INDEX")
MIC_SAMPLE_RATE = _env_opt_int("MIC_SAMPLE_RATE")
MIC_CHANNELS = int(os.getenv("MIC_CHANNELS", "1"))


# =========================
# 协议常量和工具函数
# =========================

PROTOCOL_VERSION = 0b0001
CLIENT_FULL_REQUEST = 0b0001
CLIENT_AUDIO_ONLY_REQUEST = 0b0010
SERVER_FULL_RESPONSE = 0b1001
SERVER_ACK = 0b1011
SERVER_ERROR_RESPONSE = 0b1111
MSG_WITH_EVENT = 0b0100
JSON = 0b0001
NO_SERIALIZATION = 0b0000
GZIP = 0b0001


def generate_header(
    version=PROTOCOL_VERSION,
    message_type=CLIENT_FULL_REQUEST,
    message_type_specific_flags=MSG_WITH_EVENT,
    serial_method=JSON,
    compression_type=GZIP,
    reserved_data=0x00,
    extension_header=bytes(),
):
    header = bytearray()
    header_size = int(len(extension_header) / 4) + 1
    header.append((version << 4) | header_size)
    header.append((message_type << 4) | message_type_specific_flags)
    header.append((serial_method << 4) | compression_type)
    header.append(reserved_data)
    header.extend(extension_header)
    return header


def parse_response(res):
    if isinstance(res, str):
        return {}

    header_size = res[0] & 0x0F
    message_type = res[1] >> 4
    message_type_specific_flags = res[1] & 0x0F
    serialization_method = res[2] >> 4
    message_compression = res[2] & 0x0F
    payload = res[header_size * 4 :]

    result = {}
    payload_msg = None
    payload_size = 0
    start = 0

    if message_type in {SERVER_FULL_RESPONSE, SERVER_ACK}:
        result["message_type"] = "SERVER_ACK" if message_type == SERVER_ACK else "SERVER_FULL_RESPONSE"
        if message_type_specific_flags & MSG_WITH_EVENT > 0:
            result["event"] = int.from_bytes(payload[:4], "big", signed=False)
            start += 4

        payload = payload[start:]
        session_id_size = int.from_bytes(payload[:4], "big", signed=True)
        session_id = payload[4 : session_id_size + 4]
        result["session_id"] = session_id.decode("utf-8", errors="ignore")
        payload = payload[4 + session_id_size :]
        payload_size = int.from_bytes(payload[:4], "big", signed=False)
        payload_msg = payload[4:]
    elif message_type == SERVER_ERROR_RESPONSE:
        result["message_type"] = "SERVER_ERROR"
        result["code"] = int.from_bytes(payload[:4], "big", signed=False)
        payload_size = int.from_bytes(payload[4:8], "big", signed=False)
        payload_msg = payload[8:]

    if payload_msg is None:
        return result

    if message_compression == GZIP:
        payload_msg = gzip.decompress(payload_msg)
    if serialization_method == JSON:
        payload_msg = json.loads(payload_msg.decode("utf-8"))
    elif serialization_method != NO_SERIALIZATION:
        payload_msg = payload_msg.decode("utf-8", errors="ignore")

    result["payload_msg"] = payload_msg
    result["payload_size"] = payload_size
    return result


def collect_texts(value: Any) -> List[str]:
    """尽量从服务端 payload 里提取用户识别文本和模型回复文本。"""
    texts = []
    text_keys = {
        "content",
        "text",
        "sentence",
        "utterance",
        "asr_text",
        "user_text",
        "answer",
        "reply",
        "response",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            if key in text_keys and isinstance(item, str) and item.strip():
                texts.append(item.strip())
            else:
                texts.extend(collect_texts(item))
    elif isinstance(value, list):
        for item in value:
            texts.extend(collect_texts(item))
    return texts


def merge_stream_text(current: str, incoming: str) -> str:
    """Merge streaming text whether the service sends deltas or cumulative text."""
    if not incoming:
        return current
    if not current:
        return incoming
    if incoming == current or current.endswith(incoming):
        return current
    if incoming.startswith(current):
        return incoming
    return current + incoming


def build_system_prompt() -> str:
    return SYSTEM_PROMPT.strip()


async def connect_websocket(url: str, headers: Dict[str, str]):
    connect_params = inspect.signature(websockets.connect).parameters
    header_arg = "additional_headers" if "additional_headers" in connect_params else "extra_headers"
    return await websockets.connect(url, **{header_arg: headers}, ping_interval=None)


# =========================
# WebSocket 实时对话客户端
# =========================


class RealtimeDialogClient:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.ws = None
        self.logid = ""

    async def connect(self):
        if not API_KEY:
            raise RuntimeError("请设置环境变量 VOLC_REALTIME_API_KEY。")
        headers = {
            "X-Api-Key": API_KEY,
            "X-Api-Resource-Id": RESOURCE_ID,
            "X-Api-Connect-Id": str(uuid.uuid4()),
        }
        safe_headers = {
            key: ("***" if key == "X-Api-Key" else value)
            for key, value in headers.items()
        }
        print("url: {}, headers: {}".format(BASE_URL, safe_headers))

        self.ws = await connect_websocket(BASE_URL, headers)
        self.logid = self.ws.response_headers.get("X-Tt-Logid")
        print("dialog server response logid: {}".format(self.logid))

        await self.start_connection()
        await self.start_session()

    async def start_connection(self):
        request = bytearray(generate_header())
        request.extend(int(1).to_bytes(4, "big"))
        payload_bytes = gzip.compress(b"{}")
        request.extend(len(payload_bytes).to_bytes(4, "big"))
        request.extend(payload_bytes)
        await self.ws.send(request)
        response = await self.ws.recv()
        print("StartConnection response: {}".format(parse_response(response)))

    async def start_session(self):
        request_params = {
            "asr": {
                "extra": {
                    "end_smooth_window_ms": 1500,
                },
            },
            "tts": {
                "speaker": SPEAKER,
                "audio_config": {
                    "channel": CHANNELS,
                    "format": "pcm",
                    "sample_rate": OUTPUT_SAMPLE_RATE,
                },
            },
            "dialog": {
                "bot_name": "课程助教",
                "system_role": build_system_prompt(),
                "speaking_style": "严格按照 system_role 中的提示词回答，简洁自然。",
                "extra": {
                    "model": MODEL_VERSION,
                    "strict_audit": False,
                    "audit_response": "抱歉，这个问题我暂时不能回答。",
                    "recv_timeout": RECV_TIMEOUT,
                    "input_mod": "audio",
                },
            },
        }

        print("实际写入的提示词:\n{}\n".format(request_params["dialog"]["system_role"]))

        payload_bytes = gzip.compress(json.dumps(request_params, ensure_ascii=False).encode("utf-8"))
        request = bytearray(generate_header())
        request.extend(int(100).to_bytes(4, "big"))
        request.extend(len(self.session_id).to_bytes(4, "big"))
        request.extend(self.session_id.encode("utf-8"))
        request.extend(len(payload_bytes).to_bytes(4, "big"))
        request.extend(payload_bytes)
        await self.ws.send(request)
        response = await self.ws.recv()
        print("StartSession response: {}".format(parse_response(response)))

    async def chat_text_query(self, content: str):
        payload = {"content": content}
        payload_bytes = gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        request = bytearray(generate_header())
        request.extend(int(501).to_bytes(4, "big"))
        request.extend(len(self.session_id).to_bytes(4, "big"))
        request.extend(self.session_id.encode("utf-8"))
        request.extend(len(payload_bytes).to_bytes(4, "big"))
        request.extend(payload_bytes)
        await self.ws.send(request)

    async def send_audio(self, audio: bytes):
        payload_bytes = gzip.compress(audio)
        request = bytearray(
            generate_header(
                message_type=CLIENT_AUDIO_ONLY_REQUEST,
                serial_method=NO_SERIALIZATION,
            )
        )
        request.extend(int(200).to_bytes(4, "big"))
        request.extend(len(self.session_id).to_bytes(4, "big"))
        request.extend(self.session_id.encode("utf-8"))
        request.extend(len(payload_bytes).to_bytes(4, "big"))
        request.extend(payload_bytes)
        await self.ws.send(request)

    async def receive(self):
        response = await self.ws.recv()
        return parse_response(response)

    async def finish_session(self):
        payload_bytes = gzip.compress(b"{}")
        request = bytearray(generate_header())
        request.extend(int(102).to_bytes(4, "big"))
        request.extend(len(self.session_id).to_bytes(4, "big"))
        request.extend(self.session_id.encode("utf-8"))
        request.extend(len(payload_bytes).to_bytes(4, "big"))
        request.extend(payload_bytes)
        await self.ws.send(request)

    async def finish_connection(self):
        payload_bytes = gzip.compress(b"{}")
        request = bytearray(generate_header())
        request.extend(int(2).to_bytes(4, "big"))
        request.extend(len(payload_bytes).to_bytes(4, "big"))
        request.extend(payload_bytes)
        await self.ws.send(request)
        response = await self.ws.recv()
        print("FinishConnection response: {}".format(parse_response(response)))

    async def close(self):
        if self.ws:
            await self.ws.close()


# =========================
# 音频设备和会话流程
# =========================


class AudioDeviceManager:
    """管理麦克风输入与音频输出。

    - 输入：按 索引/名称子串/系统默认 选择麦克风（Ubuntu 友好），记录实际采样率/声道供上层重采样。
    - 输出：ros1 模式发布到 ROS 话题（Ros1SpeakerStream）；pyaudio 模式本地扬声器播放；
            ros1 但无 rospy（如 Windows）时自动回退 pyaudio。
    """

    def __init__(self, output_mode: str = "pyaudio"):
        self.pyaudio = pyaudio.PyAudio()
        self.input_stream = None
        self.output_stream = None
        self.output_mode = (output_mode or "pyaudio").lower()
        # 上行采集的实际参数（open_input_stream 后填充，供重采样使用）
        self.input_rate = TARGET_SAMPLE_RATE
        self.input_channels = MIC_CHANNELS

    def _resolve_input_device(self):
        """选择输入设备，返回 (device_index, device_info)。

        优先级：MIC_DEVICE_INDEX > MIC_DEVICE_NAME 子串匹配 > 系统默认输入设备。
        在 Ubuntu 上不指定时会落到系统默认麦克风（随系统设置变化）。
        """
        # 1) 明确索引
        if MIC_DEVICE_INDEX is not None:
            try:
                info = self.pyaudio.get_device_info_by_index(MIC_DEVICE_INDEX)
                if info.get("maxInputChannels", 0) > 0:
                    return MIC_DEVICE_INDEX, info
                print(f"[MIC] 指定索引 {MIC_DEVICE_INDEX} 无输入通道，忽略。")
            except Exception as exc:
                print(f"[MIC] 指定索引 {MIC_DEVICE_INDEX} 无效: {exc}")

        # 2) 名称子串匹配（不区分大小写，需有输入通道）
        if MIC_DEVICE_NAME:
            target = MIC_DEVICE_NAME.lower()
            try:
                count = self.pyaudio.get_device_count()
            except Exception:
                count = 0
            for idx in range(count):
                try:
                    info = self.pyaudio.get_device_info_by_index(idx)
                except Exception:
                    continue
                if info.get("maxInputChannels", 0) <= 0:
                    continue
                if target in str(info.get("name", "")).lower():
                    return idx, info
            print(f"[MIC] 未匹配到名称含 '{MIC_DEVICE_NAME}' 的输入设备，回退系统默认。")

        # 3) 系统默认输入设备
        try:
            info = self.pyaudio.get_default_input_device_info()
            return int(info["index"]), info
        except Exception as exc:
            print(f"[MIC] 获取系统默认输入设备失败: {exc}，交由 PyAudio 自行选择。")
            return None, None

    def open_input_stream(self):
        idx, info = self._resolve_input_device()

        # 采样率：环境变量覆盖 > 设备默认采样率 > 16k。
        if MIC_SAMPLE_RATE is not None:
            rate = MIC_SAMPLE_RATE
        elif info and info.get("defaultSampleRate"):
            rate = int(info["defaultSampleRate"])
        else:
            rate = TARGET_SAMPLE_RATE

        channels = MIC_CHANNELS
        open_kwargs = dict(
            format=pyaudio.paInt16,
            channels=channels,
            rate=rate,
            input=True,
            frames_per_buffer=max(int(rate * 0.1), 1),  # 约 100ms 读取块
        )
        if idx is not None:
            open_kwargs["input_device_index"] = idx

        try:
            self.input_stream = self.pyaudio.open(**open_kwargs)
        except Exception as exc:
            # 设备不支持该采样率/声道时，回退 16k / 单声道 / 默认设备重试。
            print(f"[MIC] 以 rate={rate}Hz ch={channels} 打开失败({exc})，回退 16k/单声道默认设备。")
            rate, channels, idx = TARGET_SAMPLE_RATE, 1, None
            self.input_stream = self.pyaudio.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                frames_per_buffer=max(int(rate * 0.1), 1),
            )

        self.input_rate = rate
        self.input_channels = channels
        dev_name = info.get("name", "系统默认") if info else "系统默认"
        print(
            f"[MIC] 已打开麦克风: index={idx}, name={dev_name}, "
            f"rate={rate}Hz, channels={channels}（发送前统一重采样到 {TARGET_SAMPLE_RATE}Hz 单声道）"
        )
        return self.input_stream

    def open_output_stream(self):
        if self.output_mode == "ros1":
            if _HAS_ROS1:
                self.output_stream = Ros1SpeakerStream(
                    topic=ROS_AUDIO_TOPIC,
                    node_name=ROS_AUDIO_NODE_NAME,
                    queue_size=ROS_AUDIO_QUEUE_SIZE,
                    latched=False,
                    control_topic=ROS_AUDIO_CONTROL_TOPIC,
                    duplex_mode="half",
                    sample_rate=OUTPUT_SAMPLE_RATE,
                    channels=CHANNELS,
                    sample_width=2,
                )
                print(
                    f"[输出] ROS1 发布模式: topic={ROS_AUDIO_TOPIC}, "
                    f"control={ROS_AUDIO_CONTROL_TOPIC}, {OUTPUT_SAMPLE_RATE}Hz/单声道/s16le"
                )
                return self.output_stream
            print("[输出] 请求 ros1 但未检测到 rospy（可能在 Windows），自动回退本地 PyAudio 播放。")
            self.output_mode = "pyaudio"

        # 本地扬声器播放：服务端下行是 s16le，用 paInt16 保证不失真。
        self.output_stream = self.pyaudio.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=OUTPUT_SAMPLE_RATE,
            output=True,
            frames_per_buffer=CHUNK,
        )
        print(f"[输出] 本地 PyAudio 播放: {OUTPUT_SAMPLE_RATE}Hz/单声道/s16le")
        return self.output_stream

    def cleanup(self):
        if isinstance(self.input_stream, pyaudio.Stream):
            try:
                self.input_stream.stop_stream()
                self.input_stream.close()
            except Exception:
                pass
        self.input_stream = None
        if self.output_stream is not None:
            try:
                if hasattr(self.output_stream, "stop_stream"):
                    self.output_stream.stop_stream()
                if hasattr(self.output_stream, "close"):
                    self.output_stream.close()
            except Exception:
                pass
        self.output_stream = None
        try:
            self.pyaudio.terminate()
        except Exception:
            pass


class SingleFileDialog:
    def __init__(self, output_mode: str = OUTPUT_AUDIO_MODE):
        self.session_id = str(uuid.uuid4())
        self.client = RealtimeDialogClient(self.session_id)
        self.output_mode = (output_mode or "pyaudio").lower()
        self.audio_device = AudioDeviceManager(output_mode=self.output_mode)
        self.output_stream = self.audio_device.open_output_stream()
        # open_output_stream 可能因无 rospy 回退 pyaudio，这里同步实际模式
        self.output_mode = self.audio_device.output_mode
        self.audio_queue = queue.Queue()
        self.audio_buffer = b""
        self.is_running = True
        self.is_recording = True
        self.is_playing = True
        self.is_user_querying = False
        self.printed_texts = set()
        self.model_text = ""
        self.user_text = ""
        self.waiting_initial_response = False
        self.initial_response_done = asyncio.Event()

        # ---------- ROS 动作 index 发布器（关键词命中时发布 Int32） ----------
        self.action_index_topic = ACTION_INDEX_TOPIC
        self.action_index_pub = None
        self._init_action_index_publisher()

        # ---------- 下位机播放状态（订阅 /audio_playing_status，为后续全双工预留） ----------
        self.remote_playing = False
        self.remote_status_sub = None
        self._init_remote_status_subscriber()

        # ---------- LLM 输出关键短语检测缓冲（支持跨 token） ----------
        self._llm_keyword_buffer = ""
        self._llm_buffer_max_len = 50
        self._llm_kws_fired: set = set()

        # ---------- 打断/停止用的 utterance id ----------
        self._bot_utterance_id = int(time.time() * 1000) & 0x7FFFFFFF

        signal.signal(signal.SIGINT, self._keyboard_signal)

    def _keyboard_signal(self, sig, frame):
        print("\n收到 Ctrl+C，准备结束会话...")
        self.stop()

    def stop(self):
        self.is_running = False
        self.is_recording = False
        self.is_playing = False
        # 进程结束：通知下位机停止播放并清空其缓冲
        try:
            self._interrupt_playback("session_end")
        except Exception:
            pass
        # 注销 ROS 订阅
        try:
            if getattr(self, "remote_status_sub", None) is not None:
                self.remote_status_sub.unregister()
        except Exception:
            pass

    # ---------- ROS 发布/订阅初始化 ----------
    def _init_action_index_publisher(self):
        if not _HAS_ROS1 or rospy is None or Int32 is None:
            print("[KWS-ROS] 未检测到 ROS1，动作 index 话题不可用（关键词仍会检测并打印）")
            return
        try:
            if not rospy.core.is_initialized():
                rospy.init_node(
                    "action_index_publisher", anonymous=True, disable_signals=True
                )
            self.action_index_pub = rospy.Publisher(
                self.action_index_topic, Int32, queue_size=10, latch=False
            )
            print(f"[KWS-ROS] 已准备发布动作 index 话题: {self.action_index_topic}")
        except Exception as e:
            self.action_index_pub = None
            print(f"[KWS-ROS] 初始化动作 index 发布器失败: {e}")

    def _init_remote_status_subscriber(self):
        if not _HAS_ROS1 or rospy is None or Bool is None:
            return
        try:
            if not rospy.core.is_initialized():
                rospy.init_node(
                    "audio_dialog_client", anonymous=True, disable_signals=True
                )
            self.remote_status_sub = rospy.Subscriber(
                REMOTE_STATUS_TOPIC, Bool, self._remote_audio_status_callback, queue_size=10
            )
            print(f"[ROS] 已订阅下位机播放状态话题: {REMOTE_STATUS_TOPIC}")
        except Exception as e:
            print(f"[ROS] 订阅播放状态失败: {e}")

    def _remote_audio_status_callback(self, msg):
        self.remote_playing = bool(msg.data)

    # ---------- 打断（半双工：用户说话/会话结束时清队列并通知下位机） ----------
    def _is_ros_output(self) -> bool:
        return hasattr(self.output_stream, "interrupt")

    def _advance_utterance_id(self):
        self._bot_utterance_id = (int(self._bot_utterance_id) + 1) & 0x7FFFFFFF

    def _interrupt_playback(self, reason: str = "user_speech"):
        # 清空本地待播队列
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
        # ROS 输出：向 /audio/control 发 stop，让下位机立即静音并清空缓冲
        if self._is_ros_output():
            ids = [int(self._bot_utterance_id)]
            if reason == "session_end":
                ids += [int(self._bot_utterance_id) + 1, int(self._bot_utterance_id) + 2]
            for uid in sorted(set(ids)):
                try:
                    self.output_stream.interrupt(uid, reason)
                except Exception as e:
                    print(f"[打断] 发送 stop 失败(uid={uid}): {e}")
        self._advance_utterance_id()

    # ---------- 关键词 → 动作 index 发布 ----------
    def _emit_voice_keyword(self, keyword: str) -> bool:
        index = ACTION_INDEX_BY_KEYWORD.get(keyword)
        if index is None:
            print(f"[KWS-ROS] 未映射关键词，跳过发布: {keyword}")
            return False
        # 左/右等方向关键词可配置重复发送，确保下位机可靠接收并执行多次
        repeat_count = REPEAT_ACTION_COUNT.get(keyword, 1)
        pub = getattr(self, "action_index_pub", None)
        if pub is None:
            print(
                f"[KWS-ROS] 动作 index 发布器不可用（未连接 ROS）: "
                f"keyword={keyword}, index={index}, repeat={repeat_count}"
            )
            return False
        try:
            for i in range(repeat_count):
                pub.publish(Int32(data=index))
                if i < repeat_count - 1:
                    time.sleep(0.1)  # 间隔 100ms，避免下位机来不及处理
            print(
                f"[KWS-ROS] 发布动作 index: keyword={keyword}, index={index}, "
                f"repeat={repeat_count}, topic={self.action_index_topic}"
            )
            return True
        except Exception as e:
            print(f"[KWS-ROS] 发布动作 index 失败: {e}")
            return False

    def _maybe_emit_from_asr(self, payload_msg: Any):
        """从 ASR payload 抽取文本，按 KWS_PRIORITY 匹配 ASR_KWS_PATTERNS。"""
        if not isinstance(payload_msg, dict):
            return
        cand_texts = []
        for r in payload_msg.get("results", []):
            if r.get("text"):
                cand_texts.append(r["text"])
            for alt in r.get("alternatives", []):
                if alt.get("text"):
                    cand_texts.append(alt["text"])
        extra = payload_msg.get("extra", {})
        if isinstance(extra, dict) and extra.get("origin_text"):
            cand_texts.append(extra["origin_text"])
        joined = " ".join(cand_texts)
        if not joined:
            return
        # 复合方位优先（left_front > left），允许复合+简单方位同时触发
        for keyword in KWS_PRIORITY:
            patterns = ASR_KWS_PATTERNS.get(keyword)
            if patterns is None:
                continue
            if any(p in joined for p in patterns):
                self._emit_voice_keyword(keyword)
                print(f"[ASR-KWS] 检测到关键词 '{keyword}', 已发布 ROS index")

    def _detect_llm_keywords(self, content: str):
        """把模型 TTS 文本 content 累积到缓冲（保留最近若干字符），按 KWS_PRIORITY 匹配 LLM_KWS_PATTERNS。"""
        if not content:
            return
        self._llm_keyword_buffer += content
        if len(self._llm_keyword_buffer) > self._llm_buffer_max_len:
            self._llm_keyword_buffer = self._llm_keyword_buffer[-self._llm_buffer_max_len:]
        buf = self._llm_keyword_buffer
        for keyword in KWS_PRIORITY:
            patterns = LLM_KWS_PATTERNS.get(keyword)
            if patterns is None:
                continue
            if keyword in self._llm_kws_fired:  # 本轮已触发过的不重复
                continue
            if any(p in buf for p in patterns):
                self._emit_voice_keyword(keyword)
                print(f"[LLM-KWS] 检测到关键词 '{keyword}', 已发布 ROS index")
                self._llm_kws_fired.add(keyword)
                if keyword == "end":
                    self._llm_keyword_buffer = ""

    def audio_player_loop(self):
        while self.is_playing:
            try:
                audio_data = self.audio_queue.get(timeout=1.0)
                if audio_data:
                    # 下行 TTS 为 Float32 PCM，ROS/PyAudio 播放端按 int16 处理，先转换
                    audio_data = float32_pcm_to_int16(audio_data)
                    self.output_stream.write(audio_data)
            except queue.Empty:
                time.sleep(0.05)
            except Exception as exc:
                print("音频播放错误: {}".format(exc))
                time.sleep(0.1)

    def print_payload_text(self, payload_msg: Any, event: Optional[int]):
        for text in collect_texts(payload_msg):
            if event in {451, 452, 453, 459}:
                self.user_text = text
            else:
                self.model_text = merge_stream_text(self.model_text, text)

    def print_final_texts(self, event: Optional[int]):
        if event == 459 and self.user_text:
            print("用户输入: {}".format(self.user_text))
            self.user_text = ""

        if event == 359 and self.model_text:
            print("模型回复: {}".format(self.model_text))
            self.model_text = ""

    def handle_server_response(self, response: Dict[str, Any]):
        if not response:
            return

        message_type = response.get("message_type")
        payload_msg = response.get("payload_msg")

        if message_type == "SERVER_ACK" and isinstance(payload_msg, bytes):
            self.audio_queue.put(payload_msg)
            self.audio_buffer += payload_msg
            return

        if message_type == "SERVER_ERROR":
            print("服务器错误: {}".format(response))
            self.stop()
            return

        if message_type != "SERVER_FULL_RESPONSE":
            return

        event = response.get("event")
        self.print_payload_text(payload_msg, event)
        self.print_final_texts(event)

        # 每轮模型回答开始（event=553）：重置 LLM 关键词缓冲与已触发集合，并推进 utterance id
        if event == 553:
            self._llm_keyword_buffer = ""
            self._llm_kws_fired.clear()
            self._advance_utterance_id()

        # LLM 文本关键词检测（模型 TTS 文本 content，跨 token 累积）
        if isinstance(payload_msg, dict) and payload_msg.get("content"):
            self._detect_llm_keywords(payload_msg["content"])

        # ASR 文本关键词检测（用户语音识别结果，event=451）
        if event == 451:
            try:
                self._maybe_emit_from_asr(payload_msg)
            except Exception as e:
                print(f"[KWS] 解析 ASR(451) 失败: {e}")

        # 450：用户开始说话，打断播放（清本地队列 + 通知下位机停止），避免继续播旧回复。
        if event == 450:
            self._interrupt_playback("user_speech")
            self.is_user_querying = True
        # 459：用户一轮输入结束。
        elif event == 459:
            self.is_user_querying = False
        # 359：TTS 播放结束。初始开场结束后再打开麦克风，避免把开场语音录回去。
        elif event == 359 and self.waiting_initial_response:
            self.waiting_initial_response = False
            self.initial_response_done.set()
        elif event in {152, 153}:
            self.stop()

    async def receive_loop(self):
        try:
            while self.is_running:
                response = await self.client.receive()
                self.handle_server_response(response)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print("接收消息错误: {}".format(exc))
            self.stop()

    async def microphone_loop(self):
        stream = self.audio_device.open_input_stream()
        in_rate = self.audio_device.input_rate
        in_channels = self.audio_device.input_channels
        in_width = 2  # paInt16
        read_frames = max(int(in_rate * 0.1), 1)  # 约 100ms 读取块
        frame_bytes = TARGET_SAMPLE_WIDTH * TARGET_CHUNK_SAMPLES  # 20ms @16k = 640 字节
        ratecv_state = None
        loop = asyncio.get_running_loop()
        print("已打开麦克风，请讲话。按 Ctrl+C 结束。")

        def to_mono(pcm: bytes) -> bytes:
            if in_channels == 1:
                return pcm
            try:
                return audioop.tomono(pcm, in_width, 0.5, 0.5)
            except Exception as exc:
                print(f"[MIC] tomono 失败，使用原始音频: {exc}")
                return pcm

        while self.is_recording:
            try:
                audio_data = await loop.run_in_executor(
                    None, lambda: stream.read(read_frames, exception_on_overflow=False)
                )
                mono = to_mono(audio_data)
                if in_rate != TARGET_SAMPLE_RATE:
                    mono, ratecv_state = audioop.ratecv(
                        mono,
                        TARGET_SAMPLE_WIDTH,
                        TARGET_CHANNELS,
                        in_rate,
                        TARGET_SAMPLE_RATE,
                        ratecv_state,
                    )
                # 切成 20ms 帧逐帧发送（与参考系统一致）
                total = len(mono)
                offset = 0
                while total - offset >= frame_bytes:
                    await self.client.send_audio(mono[offset : offset + frame_bytes])
                    offset += frame_bytes
                await asyncio.sleep(0.005)
            except Exception as exc:
                print("读取麦克风数据出错: {}".format(exc))
                await asyncio.sleep(0.1)

    async def send_opening_query(self):
        opening_query = "请按照系统提示词开始对话，只说一句简短开场，然后等待学生回答。"
        print("用户输入: {}".format(opening_query))
        self.waiting_initial_response = True
        await self.client.chat_text_query(opening_query)

    async def start(self):
        receive_task = None
        mic_task = None
        try:
            await self.client.connect()
            asyncio.get_running_loop().run_in_executor(None, self.audio_player_loop)
            receive_task = asyncio.create_task(self.receive_loop())

            await self.send_opening_query()
            if self.waiting_initial_response:
                try:
                    await asyncio.wait_for(self.initial_response_done.wait(), timeout=60)
                except asyncio.TimeoutError:
                    print("等待初始回复结束超时，继续打开麦克风。")

            mic_task = asyncio.create_task(self.microphone_loop())
            while self.is_running:
                await asyncio.sleep(0.1)

            await self.client.finish_session()
            await asyncio.sleep(0.2)
            await self.client.finish_connection()
        finally:
            self.stop()
            for task in [receive_task, mic_task]:
                if task:
                    task.cancel()
            await self.client.close()
            self.audio_device.cleanup()
            if self.audio_buffer:
                with open("output.pcm", "wb") as file_obj:
                    file_obj.write(self.audio_buffer)
                print("已保存服务端语音到 output.pcm")


async def main():
    parser = argparse.ArgumentParser(description="single file realtime microphone dialog")
    parser.add_argument("--show_config", action="store_true", help="只打印实际 prompt，不连接服务")
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="列出所有音频设备后退出（排查 Ubuntu 麦克风/确认默认输入设备）",
    )
    parser.add_argument(
        "--output-audio-mode",
        choices=["ros1", "pyaudio"],
        default=OUTPUT_AUDIO_MODE,
        help="音频输出目标: ros1=发布到 ROS 话题(默认), pyaudio=本地扬声器播放",
    )
    args = parser.parse_args()

    if args.list_devices:
        import detect_audio_devices

        pa = pyaudio.PyAudio()
        try:
            print("========== 所有音频设备 ==========")
            detect_audio_devices.list_all_devices(pa, show_suitable_only=False)
        finally:
            pa.terminate()
        return

    if args.show_config:
        print("实际写入的提示词:\n{}\n".format(build_system_prompt()))
        print("实际发送的开场用户输入:\n请按照系统提示词开始对话，只说一句简短开场，然后等待学生回答。\n")
        return

    dialog = SingleFileDialog(output_mode=args.output_audio_mode)
    await dialog.start()


if __name__ == "__main__":
    asyncio.run(main())
