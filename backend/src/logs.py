from __future__ import annotations

from typing import Any

from . import docker, store
from .errors import AppError
from .util import run, stream_cmd


def _project(name: str) -> dict[str, Any]:
    project = store.get_project(name)
    if not project:
        raise AppError(f"项目不存在: {name}")
    return project


def tail(name: str, *, service: str | None = None, lines: int = 200, timestamps: bool = True) -> str:
    project = _project(name)
    args = docker.compose_prefix(project) + ["logs", "--no-color", "--tail", str(max(1, min(lines, 5000)))]
    if timestamps:
        args.append("--timestamps")
    if service:
        args.append(service)
    proc = run(args, cwd=docker.compose_cwd(project), check=False, timeout=60)
    if proc.returncode != 0:
        raise AppError((proc.stderr or proc.stdout or "读取日志失败").strip())
    return proc.stdout


def follow(name: str, *, service: str | None = None, lines: int = 200, timestamps: bool = True) -> int:
    project = _project(name)
    args = docker.compose_prefix(project) + ["logs", "--no-color", "--follow", "--tail", str(max(1, min(lines, 5000)))]
    if timestamps:
        args.append("--timestamps")
    if service:
        args.append(service)
    return stream_cmd(args, cwd=docker.compose_cwd(project))
