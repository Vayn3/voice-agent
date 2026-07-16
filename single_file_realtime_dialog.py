import argparse
import asyncio
import gzip
import inspect
import json
import os
import queue
import signal
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pyaudio
import websockets


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

# 音频配置。输入是麦克风 PCM 16k，输出是服务端 TTS PCM 24k。
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK = 3200

# 服务端静默等待时间，范围通常是 [10, 120]。
RECV_TIMEOUT = 120


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


@dataclass
class AudioConfig:
    bit_size: int
    channels: int
    sample_rate: int
    chunk: int


class AudioDeviceManager:
    def __init__(self):
        self.pyaudio = pyaudio.PyAudio()
        self.input_stream = None
        self.output_stream = None

    def open_input_stream(self):
        self.input_stream = self.pyaudio.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=INPUT_SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )
        return self.input_stream

    def open_output_stream(self):
        self.output_stream = self.pyaudio.open(
            format=pyaudio.paFloat32,
            channels=CHANNELS,
            rate=OUTPUT_SAMPLE_RATE,
            output=True,
            frames_per_buffer=CHUNK,
        )
        return self.output_stream

    def cleanup(self):
        for stream in [self.input_stream, self.output_stream]:
            if stream:
                stream.stop_stream()
                stream.close()
        self.pyaudio.terminate()


class SingleFileDialog:
    def __init__(self):
        self.session_id = str(uuid.uuid4())
        self.client = RealtimeDialogClient(self.session_id)
        self.audio_device = AudioDeviceManager()
        self.output_stream = self.audio_device.open_output_stream()
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
        signal.signal(signal.SIGINT, self._keyboard_signal)

    def _keyboard_signal(self, sig, frame):
        print("\n收到 Ctrl+C，准备结束会话...")
        self.stop()

    def stop(self):
        self.is_running = False
        self.is_recording = False
        self.is_playing = False

    def audio_player_loop(self):
        while self.is_playing:
            try:
                audio_data = self.audio_queue.get(timeout=1.0)
                if audio_data:
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

        # 450：用户开始说话，清掉还没播完的旧音频，避免打断后继续播旧回复。
        if event == 450:
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    break
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
        print("已打开麦克风，请讲话。按 Ctrl+C 结束。")
        while self.is_recording:
            try:
                audio_data = stream.read(CHUNK, exception_on_overflow=False)
                await self.client.send_audio(audio_data)
                await asyncio.sleep(0.01)
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
            asyncio.get_event_loop().run_in_executor(None, self.audio_player_loop)
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
    args = parser.parse_args()

    if args.show_config:
        print("实际写入的提示词:\n{}\n".format(build_system_prompt()))
        print("实际发送的开场用户输入:\n请按照系统提示词开始对话，只说一句简短开场，然后等待学生回答。\n")
        return

    dialog = SingleFileDialog()
    await dialog.start()


if __name__ == "__main__":
    asyncio.run(main())
