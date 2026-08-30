from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .errors import AppError
from .util import parse_docker_json, run


def docker_bin():
    # type: () -> str
    return "docker"


def compose_prefix(project):
    # type: (Dict[str, Any]) -> List[str]
    """构建 docker compose 命令前缀。

    必须带 --project-directory，否则相对卷（如 ./cfg/ssl）会按错误目录解析，
    导致证书挂载为空、HTTPS 失效。
    """
    compose_file = project.get("compose_file")
    if not compose_file:
        raise AppError("项目 {} 没有 compose 文件".format(project.get("name")))
    compose_path = Path(compose_file)
    project_dir = project.get("workdir") or str(compose_path.parent)
    args = [
        docker_bin(),
        "compose",
        "--project-directory",
        str(project_dir),
        "-p",
        project["name"],
        "-f",
        str(compose_path),
    ]
    env_file = project.get("env_file")
    if env_file and Path(env_file).is_file():
        args.extend(["--env-file", env_file])
    return args


def compose_cwd(project):
    # type: (Dict[str, Any]) -> Optional[str]
    workdir = project.get("workdir")
    if workdir:
        return workdir
    compose_file = project.get("compose_file")
    if compose_file:
        return str(Path(compose_file).parent)
    return None


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
    if isinstance(data, dict):
        return [data]
    return data if isinstance(data, list) else []


def _as_container_list(data):
    # type: (Any) -> List[Dict[str, Any]]
    if data is None:
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _parse_label_blob(raw):
    # type: (Any) -> Dict[str, str]
    if isinstance(raw, dict):
        return dict((str(k), str(v)) for k, v in raw.items())
    if not isinstance(raw, str) or not raw:
        return {}
    out = {}  # type: Dict[str, str]
    for part in raw.split(","):
        if "=" in part:
            key, value = part.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def _normalize_container(item):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    """统一 docker compose ps / docker ps 的字段。"""
    labels = item.get("Labels")
    if not isinstance(labels, dict):
        labels = _parse_label_blob(labels)

    name = item.get("Name") or item.get("Names") or ""
    if isinstance(name, list):
        name = name[0] if name else ""
    name = str(name).lstrip("/")

    publishers = item.get("Publishers")
    if publishers is None:
        ports_raw = item.get("Ports") or ""
        publishers = []
        if isinstance(ports_raw, list):
            publishers = ports_raw
        elif isinstance(ports_raw, str) and ports_raw.strip():
            # 例: 0.0.0.0:80->80/tcp, :::443->443/tcp
            for chunk in ports_raw.split(","):
                chunk = chunk.strip()
                if "->" in chunk:
                    left, right = chunk.split("->", 1)
                    host = left.rsplit(":", 1)[-1]
                    target = right.split("/")[0]
                    publishers.append({"PublishedPort": host, "TargetPort": target})
                elif chunk:
                    publishers.append(chunk)

    state = item.get("State") or ""
    if isinstance(state, dict):
        state = state.get("Status") or state.get("status") or ""

    return {
        "ID": item.get("ID") or item.get("Id") or "",
        "Name": name,
        "Service": item.get("Service") or labels.get("com.docker.compose.service") or "",
        "Image": item.get("Image") or "",
        "State": str(state),
        "Status": str(item.get("Status") or ""),
        "Publishers": publishers,
        "Labels": labels,
    }


def containers_by_label(project_name):
    # type: (str) -> Tuple[List[Dict[str, Any]], Optional[str]]
    """不依赖 compose 文件，按项目 label 查容器（解决 -p/文件不一致导致 ps 为空）。"""
    proc = run(
        [
            docker_bin(),
            "ps",
            "-a",
            "--filter",
            "label=com.docker.compose.project={}".format(project_name),
            "--format",
            "{{json .}}",
        ],
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return [], detail or "docker ps 失败"
    data = _as_container_list(parse_docker_json(proc.stdout))
    return [_normalize_container(item) for item in data], None


def compose_ps(project):
    # type: (Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[str]]
    """返回 (containers, error)。compose ps 为空或失败时回退到 docker ps label。"""
    err = None  # type: Optional[str]
    proc = run(
        compose_prefix(project) + ["ps", "-a", "--format", "json"],
        cwd=compose_cwd(project),
        check=False,
    )
    if proc.returncode == 0:
        data = _as_container_list(parse_docker_json(proc.stdout))
        if data:
            return [_normalize_container(item) for item in data], None
    else:
        err = (proc.stderr or proc.stdout or "").strip() or "docker compose ps 失败"

    # 回退：按 compose 项目名 label 查找（容器实际在跑但 compose 上下文对不上时）
    labeled, label_err = containers_by_label(project["name"])
    if labeled:
        return labeled, None
    if label_err:
        err = err or label_err
    return [], err


def compose_config(project):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    proc = run(
        compose_prefix(project) + ["config", "--format", "json"],
        cwd=compose_cwd(project),
    )
    data = parse_docker_json(proc.stdout)
    return data if isinstance(data, dict) else {"services": {}}
