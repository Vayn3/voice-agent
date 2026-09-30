"""Preserve source text and safely collect multi-file/ZIP submissions. Never execute uploads."""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import UploadFile

SOURCE_EXTENSIONS = {".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".hh", ".l", ".lex",
                     ".y", ".yacc", ".g4", ".java", ".py", ".js", ".ts", ".cs", ".rs",
                     ".go", ".s", ".asm", ".ll", ".pas", ".m", ".kt", ".sh", ".bat", ".ps1"}
TEXT_EXTENSIONS = SOURCE_EXTENSIONS | {".md", ".txt", ".json", ".yaml", ".yml", ".toml",
                                      ".xml", ".csv", ".cmake", ".in", ".out", ".log", ".test"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".doc"}
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS | DOCUMENT_EXTENSIONS | {".zip"}
TEXT_NAMES = {"makefile", "cmakelists.txt", "readme", "dockerfile"}
IGNORED_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".next"}
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 40 * 1024 * 1024
MAX_FILES = 200
MAX_TEXT_CHARS = 1_200_000


class SubmissionError(ValueError):
    pass


def is_allowed(name: str) -> bool:
    return Path(name).suffix.lower() in ALLOWED_EXTENSIONS or Path(name).name.lower() in TEXT_NAMES


def decode_source(data: bytes, name: str) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    if b"\x00" in data:
        raise SubmissionError(f"{name} 含二进制内容，不能作为源码/文本分析。")
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise SubmissionError(f"无法读取 {name} 编码，请使用UTF-8或GB18030保存。")


def _safe_member(name: str) -> str:
    normalized = name.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if not parts or normalized.startswith("/") or ".." in parts or any(":" in p for p in parts):
        raise SubmissionError(f"ZIP含不安全路径：{name}")
    return normalized


async def collect_submission(files: list[UploadFile], directory: Path) -> tuple[Path, list[dict[str, Any]]]:
    if not files or len(files) > 30:
        raise SubmissionError("请选择1到30个文件，可用ZIP提交项目；展开后最多200个文件。")
    directory.mkdir(parents=True, exist_ok=False)
    manifest: list[dict[str, Any]] = []
    names: set[str] = set()
    total = 0
    text_chars = 0

    def add(name: str, data: bytes, *, archived: bool = False) -> None:
        nonlocal total, text_chars
        if len(manifest) >= MAX_FILES or len(data) > MAX_FILE_BYTES:
            raise SubmissionError("文件数量超过200或单个文件超过20MB，请按阶段拆分提交。")
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise SubmissionError("提交内容（含ZIP解压后）超过40MB，请按阶段拆分。")
        if name.casefold() in names:
            raise SubmissionError(f"提交中存在重名文件：{name}")
        names.add(name.casefold())
        suffix = Path(name).suffix.lower()
        kind = "source" if suffix in SOURCE_EXTENSIONS else "document"
        if not is_allowed(name) or suffix == ".zip":
            if not archived:
                raise SubmissionError(f"不支持 {name}，请提交源码、PDF/Word/文本或ZIP。")
            manifest.append(dict(name=name, size=len(data), kind="excluded", reason="非可读源码/文档或嵌套压缩包，仅记录存在性"))
            return
        if not data:
            raise SubmissionError(f"{name} 是空文件。")
        if suffix not in DOCUMENT_EXTENSIONS:
            content = decode_source(data, name)
            text_chars += len(content)
            if text_chars > MAX_TEXT_CHARS:
                raise SubmissionError("可读文本超过120万字符，请按阶段拆分；系统不会截断源码。")
        target = directory / f"{len(manifest):03d}{suffix}"
        target.write_bytes(data)
        manifest.append(dict(name=name, size=len(data), kind=kind, stored_path=str(target),
                             sha256=hashlib.sha256(data).hexdigest()))

    for upload in files:
        name = (upload.filename or "").replace("\\", "/").split("/")[-1]
        if not name or len(name) > 255 or not is_allowed(name):
            raise SubmissionError(f"不支持文件：{name or '无文件名'}。")
        data = await upload.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise SubmissionError(f"{name} 超过20MB。")
        if Path(name).suffix.lower() != ".zip":
            add(name, data)
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                members = archive.infolist()
                if len(members) > MAX_FILES + 50:
                    raise SubmissionError("ZIP条目过多，请去掉依赖和构建产物。")
                if sum(m.file_size for m in members) + total > MAX_TOTAL_BYTES:
                    raise SubmissionError("ZIP展开后超过40MB。")
                for member in members:
                    safe_name = _safe_member(member.filename)
                    if member.flag_bits & 1 or stat.S_ISLNK(member.external_attr >> 16):
                        raise SubmissionError("不支持加密ZIP或符号链接。")
                    if member.is_dir():
                        continue
                    if member.file_size > MAX_FILE_BYTES:
                        raise SubmissionError(f"ZIP内 {safe_name} 超过20MB。")
                    if any(p in IGNORED_DIRS for p in PurePosixPath(safe_name).parts):
                        raise SubmissionError("ZIP包含依赖目录或Git目录，请移除后重新提交，避免遗漏源码。")
                    add(f"{name}/{safe_name}", archive.read(member), archived=True)
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
            raise SubmissionError(f"无法读取ZIP {name}：{exc}") from exc
    if not any(item["kind"] != "excluded" for item in manifest):
        raise SubmissionError("提交中没有可分析的源码或文档。")
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path, manifest


def public_files(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in item.items() if k != "stored_path"} for item in manifest]


def read_legacy_doc(path: Path) -> str:
    """Use a local read-only converter; provide a precise error when it is unavailable."""
    antiword = shutil.which("antiword")
    if antiword:
        result = subprocess.run([antiword, str(path)], capture_output=True, timeout=60, check=True)
        return decode_source(result.stdout, path.name)
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    with tempfile.TemporaryDirectory(prefix="voice-ta-doc-") as temporary:
        temp = Path(temporary)
        if soffice:
            subprocess.run([soffice, "-env:UserInstallation=" + (temp / "profile").as_uri(),
                            "--headless", "--convert-to", "txt:Text", "--outdir", str(temp), str(path)],
                           capture_output=True, timeout=60, check=True)
            converted = temp / f"{path.stem}.txt"
            if converted.exists():
                return decode_source(converted.read_bytes(), path.name)
        if os.name == "nt":
            # Arguments, not string interpolation, carry upload paths into PowerShell.
            script = temp / "read-doc.ps1"
            target = temp / "content.txt"
            script.write_text('''param([string]$InputPath, [string]$OutputPath)
$ErrorActionPreference = 'Stop'
$wordApp = $null; $document = $null
try {
  $wordApp = New-Object -ComObject Word.Application
  $wordApp.Visible = $false; $wordApp.DisplayAlerts = 0
  $wordApp.AutomationSecurity = 3
  $document = $wordApp.Documents.Open($InputPath, $false, $true)
  [IO.File]::WriteAllText($OutputPath, $document.Content.Text, [Text.UTF8Encoding]::new($false))
} finally {
  if ($document) { try { $document.Close(0) } catch {} }
  if ($wordApp) { try { $wordApp.Quit() } catch {} }
}
''', encoding="utf-8-sig")
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-File", str(script), str(path.resolve()), str(target)],
                           capture_output=True, timeout=60, check=False,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            if target.exists():
                return target.read_text(encoding="utf-8").replace("\r", "\n").replace("\x07", "")
    raise SubmissionError("旧版.doc解析需要本机Word、LibreOffice或antiword；请另存为.docx或PDF后提交。")
