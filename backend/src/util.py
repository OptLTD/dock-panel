import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .errors import AppError


def run(
    args,  # type: List[str]
    cwd=None,  # type: Optional[Union[str, Path]]
    stdin=None,  # type: Optional[str]
    timeout=None,  # type: Optional[int]
    check=True,  # type: bool
    env=None,  # type: Optional[Dict[str, str]]
):
    # type: (...) -> subprocess.CompletedProcess
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        proc = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            cwd=cwd,
            input=stdin,
            timeout=timeout,
            env=merged_env,
        )
    except FileNotFoundError as exc:
        raise AppError("找不到命令: {}".format(args[0]), 127) from exc
    except subprocess.TimeoutExpired as exc:
        raise AppError("命令超时: {}".format(" ".join(args)), 124) from exc
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise AppError(detail or "命令失败 ({}): {}".format(proc.returncode, " ".join(args)), proc.returncode)
    return proc


def stream_cmd(args, cwd=None):
    # type: (List[str], Optional[Union[str, Path]]) -> int
    try:
        proc = subprocess.Popen(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        raise AppError("找不到命令: {}".format(args[0]), 127) from exc
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    return proc.wait()


def parse_docker_json(stdout):
    # type: (str) -> Any
    text = stdout.strip()
    if not text:
        return []
    if text[0] in "[{":
        return json.loads(text)
    items = []  # type: List[Any]
    for line in text.splitlines():
        line = line.strip()
        if line:
            items.append(json.loads(line))
    return items


def read_payload():
    # type: () -> Dict[str, Any]
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise AppError("无效的 JSON 输入: {}".format(exc)) from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise AppError("请求体必须是 JSON 对象")
    return data


def slugify(name):
    # type: (str) -> str
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in name.strip())
    cleaned = cleaned.strip("-._")
    if not cleaned:
        raise AppError("名称无效")
    return cleaned
