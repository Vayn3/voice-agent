from __future__ import annotations

import asyncio
import gzip
import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

import websockets

from backend.app.models import SystemConfigIn


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

BASE_URL = os.getenv(
    "VOLC_REALTIME_BASE_URL",
    "wss://openspeech.bytedance.com/api/v3/realtime/dialogue",
)
RESOURCE_ID = os.getenv("VOLC_REALTIME_RESOURCE_ID", "volc.speech.dialog")
SPEAKER = os.getenv("VOLC_REALTIME_SPEAKER", "zh_male_xiaotian_jupiter_bigtts")
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
RECV_TIMEOUT = int(os.getenv("VOLC_REALTIME_RECV_TIMEOUT", "120"))


class RealtimeConfigError(RuntimeError):
    pass


@dataclass
class DialogTurn:
    question: str
    answer: str


@dataclass
class DialogTranscript:
    turns: list[DialogTurn] = field(default_factory=list)
    current_model_text: str = ""
    current_user_text: str = ""
    ended: bool = False

    def absorb_text(self, event: int | None, payload_msg: Any) -> None:
        for text in collect_texts(payload_msg):
            if event in {451, 452, 453, 459}:
                self.current_user_text = text
            else:
                self.current_model_text = merge_stream_text(self.current_model_text, text)

    def finalize_event(self, event: int | None) -> dict[str, Any] | None:
        if event == 459 and self.current_user_text:
            answer = self.current_user_text.strip()
            self.current_user_text = ""
            if answer:
                if self.turns and self.turns[-1].question and not self.turns[-1].answer:
                    self.turns[-1].answer = answer
                else:
                    self.turns.append(DialogTurn(question="", answer=answer))
                return {"type": "user_text", "text": answer}

        if event == 359 and self.current_model_text:
            question = self.current_model_text.strip()
            self.current_model_text = ""
            if question:
                if self.turns and not self.turns[-1].question:
                    self.turns[-1].question = question
                else:
                    self.turns.append(DialogTurn(question=question, answer=""))
                self.ended = is_dialog_done(question)
                return {"type": "model_text", "text": question, "ended": self.ended}

        return None

    def records(self) -> list[dict[str, str]]:
        return [
            {"question": turn.question, "answer": turn.answer}
            for turn in self.turns
            if turn.question.strip() or turn.answer.strip()
        ]


def generate_header(
    version: int = PROTOCOL_VERSION,
    message_type: int = CLIENT_FULL_REQUEST,
    message_type_specific_flags: int = MSG_WITH_EVENT,
    serial_method: int = JSON,
    compression_type: int = GZIP,
    reserved_data: int = 0x00,
    extension_header: bytes = b"",
) -> bytearray:
    header = bytearray()
    header_size = int(len(extension_header) / 4) + 1
    header.append((version << 4) | header_size)
    header.append((message_type << 4) | message_type_specific_flags)
    header.append((serial_method << 4) | compression_type)
    header.append(reserved_data)
    header.extend(extension_header)
    return header


def parse_response(res: bytes | str) -> dict[str, Any]:
    if isinstance(res, str):
        return {}

    header_size = res[0] & 0x0F
    message_type = res[1] >> 4
    message_type_specific_flags = res[1] & 0x0F
    serialization_method = res[2] >> 4
    message_compression = res[2] & 0x0F
    payload = res[header_size * 4 :]

    result: dict[str, Any] = {}
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


def collect_texts(value: Any) -> list[str]:
    texts: list[str] = []
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
    if not incoming:
        return current
    if not current:
        return incoming
    if incoming == current or current.endswith(incoming):
        return current
    if incoming.startswith(current):
        return incoming
    return current + incoming


def is_dialog_done(text: str) -> bool:
    normalized = text.replace(" ", "")
    done_markers = [
        "问答结束",
        "本次问答结束",
        "今天的问答到这里",
        "本轮问答到这里",
        "所有问题已经完成",
        "可以结束问答",
    ]
    return any(marker in normalized for marker in done_markers)


def build_realtime_system_prompt(base_prompt: str, question_plan: Any) -> str:
    question_plan_text = json.dumps(question_plan or [], ensure_ascii=False, indent=2)
    return f"""
{base_prompt}

请严格使用上面的提问计划主动主持语音问答。你需要：
1. 开场后一次只提出一个问题，等待学生回答。
2. 学生回答不充分时，最多追问两次；充分时进入下一题。
3. 不要询问与报告、课程或作业无关的个人信息。
4. 当所有高优先级问题都完成，且必要的中优先级问题也已覆盖后，用自然语言明确说出“本次问答结束”，然后简短感谢学生。

结构化问题计划如下：
{question_plan_text}
""".strip()


def _required_header_config(config: SystemConfigIn) -> tuple[str, str, str]:
    app_id = config.volc_realtime_app_id.strip() or os.getenv("VOLC_REALTIME_APP_ID", "")
    access_key = config.volc_realtime_access_key.strip() or os.getenv("VOLC_REALTIME_ACCESS_KEY", "")
    app_key = config.volc_realtime_app_key.strip() or os.getenv("VOLC_REALTIME_APP_KEY", "")
    if not app_id or not access_key or not app_key:
        raise RealtimeConfigError(
            "请先在系统配置页面填写实时语音对话的 App ID、Access Key 和 App Key。"
        )
    return app_id, access_key, app_key


class RealtimeDialogClient:
    def __init__(self, *, system_prompt: str, config: SystemConfigIn):
        self.session_id = str(uuid.uuid4())
        self.system_prompt = system_prompt
        self.config = config
        self.ws: Any = None

    async def connect(self) -> None:
        app_id, access_key, app_key = _required_header_config(self.config)
        headers = {
            "X-Api-App-ID": app_id,
            "X-Api-Access-Key": access_key,
            "X-Api-Resource-Id": RESOURCE_ID,
            "X-Api-App-Key": app_key,
            "X-Api-Connect-Id": str(uuid.uuid4()),
        }
        self.ws = await websockets.connect(BASE_URL, extra_headers=headers, ping_interval=None)
        await self.start_connection()
        await self.start_session()

    async def start_connection(self) -> None:
        request = bytearray(generate_header())
        request.extend(int(1).to_bytes(4, "big"))
        payload_bytes = gzip.compress(b"{}")
        request.extend(len(payload_bytes).to_bytes(4, "big"))
        request.extend(payload_bytes)
        await self.ws.send(request)
        parse_response(await self.ws.recv())

    async def start_session(self) -> None:
        request_params = {
            "asr": {"extra": {"end_smooth_window_ms": 1500}},
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
                "system_role": self.system_prompt,
                "speaking_style": "严格按照 system_role 中的提示词提问，表达简洁、自然、适合口语。",
                "extra": {
                    "strict_audit": False,
                    "audit_response": "抱歉，这个问题我暂时不能回答。",
                    "recv_timeout": RECV_TIMEOUT,
                    "input_mod": "audio",
                },
            },
        }
        payload_bytes = gzip.compress(json.dumps(request_params, ensure_ascii=False).encode("utf-8"))
        request = bytearray(generate_header())
        request.extend(int(100).to_bytes(4, "big"))
        request.extend(len(self.session_id).to_bytes(4, "big"))
        request.extend(self.session_id.encode("utf-8"))
        request.extend(len(payload_bytes).to_bytes(4, "big"))
        request.extend(payload_bytes)
        await self.ws.send(request)
        parse_response(await self.ws.recv())

    async def chat_text_query(self, content: str) -> None:
        payload = {"content": content}
        payload_bytes = gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        request = bytearray(generate_header())
        request.extend(int(501).to_bytes(4, "big"))
        request.extend(len(self.session_id).to_bytes(4, "big"))
        request.extend(self.session_id.encode("utf-8"))
        request.extend(len(payload_bytes).to_bytes(4, "big"))
        request.extend(payload_bytes)
        await self.ws.send(request)

    async def send_audio(self, audio: bytes) -> None:
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

    async def receive(self) -> dict[str, Any]:
        return parse_response(await self.ws.recv())

    async def finish_session(self) -> None:
        payload_bytes = gzip.compress(b"{}")
        request = bytearray(generate_header())
        request.extend(int(102).to_bytes(4, "big"))
        request.extend(len(self.session_id).to_bytes(4, "big"))
        request.extend(self.session_id.encode("utf-8"))
        request.extend(len(payload_bytes).to_bytes(4, "big"))
        request.extend(payload_bytes)
        await self.ws.send(request)

    async def finish_connection(self) -> None:
        payload_bytes = gzip.compress(b"{}")
        request = bytearray(generate_header())
        request.extend(int(2).to_bytes(4, "big"))
        request.extend(len(payload_bytes).to_bytes(4, "big"))
        request.extend(payload_bytes)
        await self.ws.send(request)
        try:
            await asyncio.wait_for(self.ws.recv(), timeout=3)
        except asyncio.TimeoutError:
            pass

    async def close(self) -> None:
        if self.ws:
            await self.ws.close()
