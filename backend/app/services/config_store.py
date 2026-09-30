from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from backend.app.models import SystemConfigIn, SystemConfigOut

BASE_DIR = Path(__file__).resolve().parents[3]
CONFIG_PATH = BASE_DIR / "data" / "config.json"
DEFAULT_REALTIME_MODEL_VERSION = "1.2.1.1"


class MissingConfigError(RuntimeError):
    pass


class FileConfigStore:
    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self._path = path
        self._lock = Lock()

    def read_private(self) -> SystemConfigIn:
        with self._lock:
            if not self._path.exists():
                return SystemConfigIn()
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return SystemConfigIn(**data)

    def read_public(self) -> SystemConfigOut:
        config = self.read_private()
        api_key = config.dashscope_api_key.strip()
        realtime_api_key = config.volc_realtime_api_key.strip()
        return SystemConfigOut(
            configured=bool(api_key),
            dashscope_api_key_masked=_mask_key(api_key),
            dashscope_base_url=config.dashscope_base_url,
            dashscope_text_model=config.dashscope_text_model,
            dashscope_code_model=config.dashscope_code_model,
            realtime_configured=bool(realtime_api_key),
            volc_realtime_api_key_masked=_mask_key(realtime_api_key),
            volc_realtime_model_version=(
                config.volc_realtime_model_version.strip() or DEFAULT_REALTIME_MODEL_VERSION
            ),
        )

    def save(self, config: SystemConfigIn) -> SystemConfigOut:
        current = self.read_private()
        api_key = config.dashscope_api_key.strip() or current.dashscope_api_key.strip()
        realtime_api_key = config.volc_realtime_api_key.strip() or current.volc_realtime_api_key.strip()
        normalized = SystemConfigIn(
            dashscope_api_key=api_key,
            dashscope_base_url=config.dashscope_base_url.strip()
            or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            dashscope_text_model=config.dashscope_text_model.strip() or "qwen-long",
            dashscope_code_model=config.dashscope_code_model.strip() or "qwen3-coder-plus",
            volc_realtime_api_key=realtime_api_key,
            volc_realtime_model_version=(
                config.volc_realtime_model_version.strip() or DEFAULT_REALTIME_MODEL_VERSION
            ),
        )
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                normalized.model_dump_json(indent=2),
                encoding="utf-8",
            )
        return self.read_public()

    def require_private(self) -> SystemConfigIn:
        config = self.read_private()
        if not config.dashscope_api_key.strip():
            raise MissingConfigError("请先在系统配置页面填写 DashScope API Key。")
        return config


def _mask_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}{'*' * max(len(api_key) - 8, 4)}{api_key[-4:]}"


config_store = FileConfigStore()
