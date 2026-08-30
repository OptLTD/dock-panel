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
    cmds, cwd = docker.logs_args(
        project, follow=False, service=service, lines=lines, timestamps=timestamps
    )
    chunks = []
    last_err = ""
    for args in cmds:
        proc = run(args, cwd=cwd, check=False, timeout=60)
        if proc.returncode != 0:
            last_err = (proc.stderr or proc.stdout or "读取日志失败").strip()
            continue
        text = proc.stdout or ""
        if len(cmds) > 1:
            header = args[-1] if args else "container"
            chunks.append("----- {} -----\n{}".format(header, text))
        else:
            chunks.append(text)
    if not chunks:
        raise AppError(last_err or "读取日志失败")
    return "\n".join(chunks)


def follow(name, service=None, lines=200, timestamps=True):
    # type: (str, Optional[str], int, bool) -> int
    project = _project(name)
    cmds, cwd = docker.logs_args(
        project, follow=True, service=service, lines=lines, timestamps=timestamps
    )
    # follow 只跑第一条命令
    return stream_cmd(cmds[0], cwd=cwd)
