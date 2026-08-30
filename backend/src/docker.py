from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .errors import AppError
from .util import parse_docker_json, run

_flavor_cache = None  # type: Optional[str]


def docker_bin():
    # type: () -> str
    return "docker"


def compose_flavor():
    # type: () -> str
    """返回 'docker'（Compose V2 插件）或 'podman'（podman-compose 兼容层）。"""
    global _flavor_cache
    if _flavor_cache:
        return _flavor_cache
    help_proc = run([docker_bin(), "compose", "--help"], check=False)
    help_text = ((help_proc.stdout or "") + "\n" + (help_proc.stderr or "")).lower()
    ver_proc = run([docker_bin(), "compose", "version"], check=False)
    ver_text = ((ver_proc.stdout or "") + "\n" + (ver_proc.stderr or "")).lower()
    blob = help_text + "\n" + ver_text
    if (
        "podman-compose" in blob
        or "external compose provider" in blob
        or "--project-directory" not in help_text
    ):
        _flavor_cache = "podman"
    else:
        _flavor_cache = "docker"
    return _flavor_cache


def compose_prefix(project):
    # type: (Dict[str, Any]) -> List[str]
    """构建 compose 命令前缀。

    Docker Compose V2 使用 --project-directory。
    podman-compose 不支持该参数，误传会把目录当成子命令（invalid choice: '/data'）。
    podman 场景改为依赖 cwd + -f/-p。
    """
    compose_file = project.get("compose_file")
    if not compose_file:
        raise AppError("项目 {} 没有 compose 文件".format(project.get("name")))
    compose_path = Path(compose_file)
    args = [docker_bin(), "compose"]
    if compose_flavor() == "docker":
        project_dir = project.get("workdir") or str(compose_path.parent)
        args.extend(["--project-directory", str(project_dir)])
    args.extend(["-p", project["name"], "-f", str(compose_path)])
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
        "flavor": None,
        "version": None,
        "compose_version": None,
        "error": None,
    }  # type: Dict[str, Any]
    try:
        ver = run([docker_bin(), "version", "--format", "{{.Server.Version}}"])
        info["docker"] = True
        info["version"] = ver.stdout.strip()
    except AppError as exc:
        # podman 的 docker 兼容层有时不支持该 format，再试一次
        raw = run([docker_bin(), "version"], check=False)
        if raw.returncode == 0:
            info["docker"] = True
            info["version"] = (raw.stdout or "").strip().splitlines()[0] if raw.stdout else "podman"
        else:
            info["error"] = exc.message
            return info
    try:
        flavor = compose_flavor()
        info["flavor"] = flavor
        compose = run([docker_bin(), "compose", "version"], check=False)
        text = ((compose.stdout or "") + "\n" + (compose.stderr or "")).strip()
        if compose.returncode == 0 or "podman-compose" in text.lower() or "compose" in text.lower():
            info["compose"] = True
            info["compose_version"] = text.splitlines()[0] if text else flavor
        else:
            info["error"] = text or "compose 不可用"
    except AppError as exc:
        info["error"] = exc.message
    return info


def compose_ls():
    # type: () -> List[Dict[str, Any]]
    # podman-compose 往往没有 ls；失败则返回空，靠 label 回退
    if compose_flavor() == "podman":
        return []
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


def _parse_ports(ports_raw):
    # type: (Any) -> List[Any]
    publishers = []  # type: List[Any]
    if ports_raw is None:
        return publishers
    if isinstance(ports_raw, list):
        for item in ports_raw:
            if isinstance(item, dict):
                host = (
                    item.get("PublishedPort")
                    or item.get("host_port")
                    or item.get("HostPort")
                    or item.get("publicPort")
                )
                target = (
                    item.get("TargetPort")
                    or item.get("container_port")
                    or item.get("ContainerPort")
                    or item.get("privatePort")
                )
                if host and target:
                    publishers.append({"PublishedPort": str(host), "TargetPort": str(target)})
                elif item.get("host_port") or item.get("container_port"):
                    publishers.append(
                        {
                            "PublishedPort": str(item.get("host_port") or ""),
                            "TargetPort": str(item.get("container_port") or ""),
                        }
                    )
                else:
                    publishers.append(item)
            elif isinstance(item, str) and item.strip():
                publishers.extend(_parse_ports(item))
        return publishers
    if isinstance(ports_raw, dict):
        # docker inspect NetworkSettings.Ports: {"80/tcp":[{"HostIp":"0.0.0.0","HostPort":"80"}]}
        for key, bindings in ports_raw.items():
            target = str(key).split("/")[0]
            if not bindings:
                continue
            for bind in bindings:
                if isinstance(bind, dict):
                    host = bind.get("HostPort") or bind.get("host_port")
                    if host:
                        publishers.append({"PublishedPort": str(host), "TargetPort": target})
        return publishers
    if isinstance(ports_raw, str) and ports_raw.strip():
        for chunk in ports_raw.split(","):
            chunk = chunk.strip()
            if "->" in chunk:
                left, right = chunk.split("->", 1)
                host = left.rsplit(":", 1)[-1]
                target = right.split("/")[0]
                publishers.append({"PublishedPort": host, "TargetPort": target})
            elif chunk:
                publishers.append(chunk)
    return publishers


def _normalize_container(item):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    """统一 docker/podman ps 字段。"""
    labels = item.get("Labels")
    if not isinstance(labels, dict):
        labels = _parse_label_blob(labels)

    name = item.get("Name") or item.get("Names") or item.get("Id") or ""
    if isinstance(name, list):
        name = name[0] if name else ""
    name = str(name).lstrip("/")

    publishers = item.get("Publishers")
    if publishers is None:
        publishers = _parse_ports(item.get("Ports"))

    state = item.get("State") or item.get("Status") or ""
    if isinstance(state, dict):
        state = state.get("Status") or state.get("status") or state.get("Status") or ""

    return {
        "ID": item.get("ID") or item.get("Id") or "",
        "Name": name,
        "Service": item.get("Service")
        or labels.get("com.docker.compose.service")
        or labels.get("io.podman.compose.service")
        or "",
        "Image": item.get("Image") or item.get("ImageName") or "",
        "State": str(state),
        "Status": str(item.get("Status") or state or ""),
        "Publishers": publishers if publishers is not None else [],
        "Labels": labels,
    }


def _enrich_ports_from_inspect(containers):
    # type: (List[Dict[str, Any]]) -> List[Dict[str, Any]]
    """ps 没带端口时，用 inspect 补 HostPort。"""
    for item in containers:
        pubs = item.get("Publishers") or []
        if pubs:
            continue
        cid = item.get("ID") or item.get("Name")
        if not cid:
            continue
        proc = run([docker_bin(), "inspect", str(cid), "--format", "{{json .NetworkSettings.Ports}}"], check=False)
        if proc.returncode != 0 or not (proc.stdout or "").strip():
            # podman 有时要用另一种路径
            proc = run([docker_bin(), "inspect", str(cid)], check=False)
            if proc.returncode != 0:
                continue
            try:
                data = parse_docker_json(proc.stdout)
                if isinstance(data, list) and data:
                    data = data[0]
                if not isinstance(data, dict):
                    continue
                ports = (data.get("NetworkSettings") or {}).get("Ports")
            except Exception:
                continue
        else:
            ports = parse_docker_json(proc.stdout)
        item["Publishers"] = _parse_ports(ports)
    return containers


def containers_by_label(project_name):
    # type: (str) -> Tuple[List[Dict[str, Any]], Optional[str]]
    """按 compose 项目 label 查容器（兼容 docker / podman）。"""
    errors = []  # type: List[str]
    found = []  # type: List[Dict[str, Any]]
    filters = [
        "label=com.docker.compose.project={}".format(project_name),
        "label=io.podman.compose.project={}".format(project_name),
    ]
    for filt in filters:
        proc = run(
            [docker_bin(), "ps", "-a", "--filter", filt, "--format", "{{json .}}"],
            check=False,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            if detail:
                errors.append(detail)
            continue
        data = _as_container_list(parse_docker_json(proc.stdout))
        for item in data:
            found.append(_normalize_container(item))
        if found:
            break
    if not found and not errors:
        # 部分 podman 不支持 --format json，退回表格再 inspect
        proc = run([docker_bin(), "ps", "-a", "--filter", filters[0], "--format", "{{.ID}}"], check=False)
        if proc.returncode == 0 and (proc.stdout or "").strip():
            for cid in proc.stdout.split():
                insp = run([docker_bin(), "inspect", cid], check=False)
                if insp.returncode != 0:
                    continue
                payload = parse_docker_json(insp.stdout)
                if isinstance(payload, list) and payload:
                    payload = payload[0]
                if isinstance(payload, dict):
                    found.append(_normalize_container(_inspect_to_row(payload)))
    if found:
        return _enrich_ports_from_inspect(found), None
    return [], (errors[0] if errors else None)


def _inspect_to_row(data):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    name = data.get("Name") or ""
    state = data.get("State") or {}
    labels = (data.get("Config") or {}).get("Labels") or {}
    return {
        "ID": data.get("Id") or "",
        "Names": name,
        "Image": (data.get("Config") or {}).get("Image") or "",
        "State": state.get("Status") if isinstance(state, dict) else state,
        "Status": state.get("Status") if isinstance(state, dict) else state,
        "Labels": labels,
        "Ports": (data.get("NetworkSettings") or {}).get("Ports"),
    }


def compose_ps(project):
    # type: (Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[str]]
    """返回 (containers, error)。优先 label；docker 时再试 compose ps。"""
    labeled, label_err = containers_by_label(project["name"])
    if labeled:
        return labeled, None

    if compose_flavor() == "podman":
        return [], label_err or "未找到项目容器（podman）。请确认容器 label 含 compose 项目名。"

    err = label_err
    proc = run(
        compose_prefix(project) + ["ps", "-a", "--format", "json"],
        cwd=compose_cwd(project),
        check=False,
    )
    if proc.returncode == 0:
        data = _as_container_list(parse_docker_json(proc.stdout))
        if data:
            rows = [_normalize_container(item) for item in data]
            return _enrich_ports_from_inspect(rows), None
    else:
        detail = (proc.stderr or proc.stdout or "").strip()
        err = detail or err or "docker compose ps 失败"
    return [], err


def compose_config(project):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    proc = run(
        compose_prefix(project) + ["config"],
        cwd=compose_cwd(project),
        check=False,
    )
    # podman-compose config 不一定支持 --format json
    if proc.returncode != 0:
        raise AppError((proc.stderr or proc.stdout or "compose config 失败").strip())
    text = proc.stdout or ""
    if text.lstrip().startswith("{"):
        data = parse_docker_json(text)
        return data if isinstance(data, dict) else {"services": {}}
    return {"raw": text, "services": {}}


def logs_args(project, follow=False, service=None, lines=200, timestamps=True):
    # type: (Dict[str, Any], bool, Optional[str], int, bool) -> Tuple[List[List[str]], Optional[str]]
    """返回 (命令列表, cwd)。可能多条 docker logs，调用方按序执行。"""
    lines = max(1, min(int(lines), 5000))
    cwd = compose_cwd(project)
    containers, _err = containers_by_label(project["name"])
    selected = []  # type: List[Dict[str, Any]]
    for item in containers:
        if service:
            if item.get("Service") == service or item.get("Name") == service:
                selected.append(item)
        else:
            selected.append(item)

    def one_logs(name, do_follow):
        # type: (str, bool) -> List[str]
        args = [docker_bin(), "logs", "--tail", str(lines)]
        if timestamps:
            args.append("-t")
        if do_follow:
            args.append("-f")
        args.append(str(name))
        return args

    if selected:
        if follow:
            # follow 只能跟一个流；有指定 service 或仅一容器时用 docker logs
            if service or len(selected) == 1:
                target = selected[0].get("Name") or selected[0].get("ID")
                return [one_logs(str(target), True)], cwd
        else:
            cmds = []
            for item in selected:
                target = item.get("Name") or item.get("ID")
                if target:
                    cmds.append(one_logs(str(target), False))
            if cmds:
                return cmds, cwd

    args = compose_prefix(project) + ["logs", "--tail", str(lines)]
    if follow:
        args.append("--follow")
    if timestamps:
        args.append("-t")
    if service:
        args.append(service)
    return [args], cwd
