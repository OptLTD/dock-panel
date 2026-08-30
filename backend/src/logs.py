from typing import Any, Dict, Optional

from . import docker, store
from .errors import AppError
from .util import run, stream_cmd


def _project(name):
    # type: (str) -> Dict[str, Any]
    project = store.get_project(name)
    if not project:
        raise AppError("项目不存在: {}".format(name))
    return project


def tail(name, service=None, lines=200, timestamps=True):
    # type: (str, Optional[str], int, bool) -> str
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


def follow(name, service=None, lines=200, timestamps=True):
    # type: (str, Optional[str], int, bool) -> int
    project = _project(name)
    args = docker.compose_prefix(project) + ["logs", "--no-color", "--follow", "--tail", str(max(1, min(lines, 5000)))]
    if timestamps:
        args.append("--timestamps")
    if service:
        args.append(service)
    return stream_cmd(args, cwd=docker.compose_cwd(project))
