from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .errors import AppError


def run(
    args: list[str],
    *,
    cwd: str | Path | None = None,
    stdin: str | None = None,
    timeout: int | None = None,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=cwd,
            input=stdin,
            timeout=timeout,
            env=merged_env,
        )
    except FileNotFoundError as exc:
        raise AppError(f"找不到命令: {args[0]}", 127) from exc
    except subprocess.TimeoutExpired as exc:
        raise AppError(f"命令超时: {' '.join(args)}", 124) from exc
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise AppError(detail or f"命令失败 ({proc.returncode}): {' '.join(args)}", proc.returncode)
    return proc


def stream_cmd(args: list[str], *, cwd: str | Path | None = None) -> int:
    try:
        proc = subprocess.Popen(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        raise AppError(f"找不到命令: {args[0]}", 127) from exc
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    return proc.wait()


def parse_docker_json(stdout: str) -> Any:
    text = stdout.strip()
    if not text:
        return []
    if text[0] in "[{":
        return json.loads(text)
    items: list[Any] = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            items.append(json.loads(line))
    return items


def read_payload() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(f"无效的 JSON 输入: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise AppError("请求体必须是 JSON 对象")
    return data


def slugify(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in name.strip())
    cleaned = cleaned.strip("-._")
    if not cleaned:
        raise AppError("名称无效")
    return cleaned
