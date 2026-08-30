from pathlib import Path
from typing import Any, Dict, List, Optional

from .errors import AppError
from .util import parse_docker_json, run


def docker_bin():
    # type: () -> str
    return "docker"


def compose_prefix(project):
    # type: (Dict[str, Any]) -> List[str]
    compose_file = project.get("compose_file")
    if not compose_file:
        raise AppError("项目 {} 没有 compose 文件".format(project.get("name")))
    args = [docker_bin(), "compose", "-p", project["name"], "-f", compose_file]
    env_file = project.get("env_file")
    if env_file and Path(env_file).is_file():
        args.extend(["--env-file", env_file])
    return args


def compose_cwd(project):
    # type: (Dict[str, Any]) -> Optional[str]
    workdir = project.get("workdir")
    return workdir if workdir else None


def engine_info():
    # type: () -> Dict[str, Any]
    info = {
        "docker": False,
        "compose": False,
        "version": None,
        "compose_version": None,
        "error": None,
    }  # type: Dict[str, Any]
    try:
        ver = run([docker_bin(), "version", "--format", "{{.Server.Version}}"])
        info["docker"] = True
        info["version"] = ver.stdout.strip()
    except AppError as exc:
        info["error"] = exc.message
        return info
    try:
        compose = run([docker_bin(), "compose", "version", "--short"])
        info["compose"] = True
        info["compose_version"] = compose.stdout.strip()
    except AppError as exc:
        info["error"] = exc.message
    return info


def compose_ls():
    # type: () -> List[Dict[str, Any]]
    proc = run([docker_bin(), "compose", "ls", "-a", "--format", "json"], check=False)
    if proc.returncode != 0:
        return []
    data = parse_docker_json(proc.stdout)
    return data if isinstance(data, list) else []


def compose_ps(project):
    # type: (Dict[str, Any]) -> List[Dict[str, Any]]
    proc = run(
        compose_prefix(project) + ["ps", "-a", "--format", "json"],
        cwd=compose_cwd(project),
        check=False,
    )
    if proc.returncode != 0:
        return []
    data = parse_docker_json(proc.stdout)
    return data if isinstance(data, list) else []


def compose_config(project):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    proc = run(
        compose_prefix(project) + ["config", "--format", "json"],
        cwd=compose_cwd(project),
    )
    data = parse_docker_json(proc.stdout)
    return data if isinstance(data, dict) else {"services": {}}
