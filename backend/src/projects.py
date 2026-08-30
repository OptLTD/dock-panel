import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from . import docker, paths, store
from .errors import AppError
from .util import slugify, stream_cmd


def _now():
    # type: () -> str
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_name(name):
    # type: (str) -> str
    name = slugify(name)
    if "/" in name or name.startswith("."):
        raise AppError("项目名称不合法")
    return name


def _status_from_ps(containers):
    # type: (List[Dict[str, Any]]) -> Dict[str, Any]
    running = 0
    total = len(containers)
    ports = []  # type: List[str]
    services = []  # type: List[Dict[str, Any]]
    for item in containers:
        state = str(item.get("State") or "").lower()
        status = str(item.get("Status") or "")
        health = "running" if state in ("running", "up") else state or "unknown"
        if health == "running":
            running += 1
        published = item.get("Publishers") or item.get("Ports") or []
        svc_ports = []  # type: List[str]
        if isinstance(published, list):
            for pub in published:
                if isinstance(pub, dict):
                    host = pub.get("PublishedPort") or pub.get("URL")
                    target = pub.get("TargetPort") or pub.get("Target")
                    if host and target:
                        text = "{}:{}".format(host, target)
                        svc_ports.append(str(text))
                        ports.append(str(text))
                elif isinstance(pub, str) and pub:
                    svc_ports.append(pub)
                    ports.append(pub)
        elif isinstance(published, str) and published:
            svc_ports.append(published)
            ports.append(published)
        labels = item.get("Labels") if isinstance(item.get("Labels"), dict) else {}
        services.append(
            {
                "id": item.get("ID") or item.get("Id") or "",
                "name": item.get("Name") or item.get("Names") or "",
                "service": item.get("Service") or labels.get("com.docker.compose.service") or "",
                "image": item.get("Image") or "",
                "state": health,
                "status": status,
                "ports": svc_ports,
            }
        )
    if total == 0:
        summary = "empty"
    elif running == total:
        summary = "running"
    elif running == 0:
        summary = "stopped"
    else:
        summary = "partial"
    # preserve order, unique
    uniq_ports = []  # type: List[str]
    seen = set()
    for port in ports:
        if port not in seen:
            seen.add(port)
            uniq_ports.append(port)
    return {
        "summary": summary,
        "running": running,
        "total": total,
        "ports": uniq_ports,
        "services": services,
    }


def _enrich(project):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    item = dict(project)
    compose_file = item.get("compose_file")
    item["compose_exists"] = bool(compose_file and Path(compose_file).is_file())
    if item["compose_exists"]:
        try:
            item.update(_status_from_ps(docker.compose_ps(item)))
        except Exception as exc:  # noqa: BLE001
            item["summary"] = "error"
            item["running"] = 0
            item["total"] = 0
            item["ports"] = []
            item["services"] = []
            item["error"] = str(exc)
    else:
        item["summary"] = "missing"
        item["running"] = 0
        item["total"] = 0
        item["ports"] = []
        item["services"] = []
    item.setdefault("certs", [])
    return item


def list_projects():
    # type: () -> List[Dict[str, Any]]
    registered = [_enrich(p) for p in store.load_projects()]
    known = set(p["name"] for p in registered)
    known_files = set(p.get("compose_file") for p in registered)
    extras = []  # type: List[Dict[str, Any]]
    for stack in docker.compose_ls():
        name = stack.get("Name") or stack.get("name")
        config = stack.get("ConfigFiles") or stack.get("configFiles") or ""
        compose_file = config.split(",")[0].strip() if config else ""
        if not name or name in known or (compose_file and compose_file in known_files):
            continue
        extras.append(
            _enrich(
                {
                    "name": name,
                    "compose_file": compose_file,
                    "workdir": str(Path(compose_file).parent) if compose_file else "",
                    "managed": False,
                    "unregistered": True,
                    "source": "compose-ls",
                    "certs": [],
                }
            )
        )
    return registered + extras


def get_project(name, required=True):
    # type: (str, bool) -> Dict[str, Any]
    item = store.get_project(name)
    if item:
        return _enrich(item)
    for found in list_projects():
        if found["name"] == name:
            return found
    raise AppError("项目不存在: {}".format(name))


def register(payload):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    compose_file = Path(payload.get("compose_file") or "").expanduser()
    if not compose_file.is_file():
        raise AppError("compose 文件不存在: {}".format(compose_file))
    name = _validate_name(payload.get("name") or compose_file.parent.name)
    workdir = str(Path(payload.get("workdir") or compose_file.parent).expanduser())
    env_file = payload.get("env_file")
    if env_file:
        env_path = Path(env_file).expanduser()
        if not env_path.is_file():
            raise AppError("env 文件不存在: {}".format(env_path))
        env_file = str(env_path)
    else:
        guessed = Path(workdir) / ".env"
        env_file = str(guessed) if guessed.is_file() else ""

    with store.locked_projects() as items:
        if any(p["name"] == name for p in items):
            raise AppError("项目已存在: {}".format(name))
        record = {
            "name": name,
            "compose_file": str(compose_file.resolve()),
            "workdir": workdir,
            "env_file": env_file,
            "managed": False,
            "notes": payload.get("notes") or "",
            "certs": payload.get("certs") or [],
            "created_at": _now(),
            "updated_at": _now(),
        }
        items.append(record)
    return _enrich(record)


def unregister(name):
    # type: (str) -> Dict[str, Any]
    name = _validate_name(name)
    with store.locked_projects() as items:
        for index, item in enumerate(items):
            if item["name"] == name:
                items.pop(index)
                return {"removed": name, "managed": item.get("managed", False)}
    raise AppError("项目不存在: {}".format(name))


def _yaml_quote(value):
    # type: (str) -> str
    if value == "" or any(ch in value for ch in ":#{}[]&*?|>!%@`'\"\\ \t"):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def render_compose(services, project_name):
    # type: (List[Dict[str, Any]], str) -> str
    if not services:
        raise AppError("至少需要一个服务")
    lines = ["services:"]
    for svc in services:
        name = slugify(str(svc.get("name") or ""))
        image = str(svc.get("image") or "").strip()
        if not image:
            raise AppError("服务 {} 缺少 image".format(name))
        lines.append("  {}:".format(name))
        lines.append("    image: {}".format(image))
        restart = str(svc.get("restart") or "unless-stopped")
        lines.append("    restart: {}".format(restart))
        command = svc.get("command")
        if command:
            lines.append("    command: {}".format(_yaml_quote(str(command))))
        ports = svc.get("ports") or []
        if ports:
            lines.append("    ports:")
            for port in ports:
                lines.append("      - {}".format(_yaml_quote(str(port))))
        volumes = svc.get("volumes") or []
        if volumes:
            lines.append("    volumes:")
            for volume in volumes:
                lines.append("      - {}".format(_yaml_quote(str(volume))))
        environment = svc.get("environment") or {}
        if isinstance(environment, dict) and environment:
            lines.append("    environment:")
            for key, value in environment.items():
                lines.append("      {}: {}".format(key, _yaml_quote(str(value))))
        elif isinstance(environment, list) and environment:
            lines.append("    environment:")
            for item in environment:
                lines.append("      - {}".format(_yaml_quote(str(item))))
        extra_hosts = svc.get("extra_hosts") or []
        if extra_hosts:
            lines.append("    extra_hosts:")
            for host in extra_hosts:
                lines.append("      - {}".format(_yaml_quote(str(host))))
        depends_on = svc.get("depends_on") or []
        if depends_on:
            lines.append("    depends_on:")
            for dep in depends_on:
                lines.append("      - {}".format(slugify(str(dep))))
        lines.append("    labels:")
        lines.append("      dock-panel.project: {}".format(project_name))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def create(payload):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    name = _validate_name(payload.get("name") or "")
    managed_dir = paths.MANAGED_DIR / name
    compose_file = managed_dir / "compose.yaml"
    if store.get_project(name):
        raise AppError("项目已存在: {}".format(name))
    if managed_dir.exists():
        raise AppError("托管目录已存在: {}".format(managed_dir))

    yaml_text = payload.get("compose_yaml")
    if yaml_text:
        content = str(yaml_text)
    else:
        content = render_compose(payload.get("services") or [], project_name=name)

    managed_dir.mkdir(parents=True, exist_ok=True)
    compose_file.write_text(content, encoding="utf-8")
    env_text = payload.get("env_text")
    env_file = ""
    if env_text is not None:
        env_path = managed_dir / ".env"
        env_path.write_text(str(env_text), encoding="utf-8")
        env_file = str(env_path)

    record = {
        "name": name,
        "compose_file": str(compose_file),
        "workdir": str(managed_dir),
        "env_file": env_file,
        "managed": True,
        "notes": payload.get("notes") or "",
        "certs": payload.get("certs") or [],
        "created_at": _now(),
        "updated_at": _now(),
    }
    with store.locked_projects() as items:
        if any(p["name"] == name for p in items):
            shutil.rmtree(managed_dir, ignore_errors=True)
            raise AppError("项目已存在: {}".format(name))
        items.append(record)
    return _enrich(record)


def update_compose(name, payload):
    # type: (str, Dict[str, Any]) -> Dict[str, Any]
    project = store.get_project(_validate_name(name))
    if not project:
        raise AppError("项目不存在: {}".format(name))
    compose_file = Path(project["compose_file"])
    yaml_text = payload.get("compose_yaml")
    if yaml_text is None:
        raise AppError("缺少 compose_yaml")
    compose_file.parent.mkdir(parents=True, exist_ok=True)
    compose_file.write_text(str(yaml_text), encoding="utf-8")
    if "env_text" in payload:
        env_path = Path(project["env_file"]) if project.get("env_file") else Path(project["workdir"]) / ".env"
        env_path.write_text(str(payload.get("env_text") or ""), encoding="utf-8")
        project["env_file"] = str(env_path)
    if "notes" in payload:
        project["notes"] = payload.get("notes") or ""
    project["updated_at"] = _now()
    with store.locked_projects() as items:
        for index, item in enumerate(items):
            if item["name"] == project["name"]:
                items[index] = project
                break
    return _enrich(project)


def read_files(name):
    # type: (str) -> Dict[str, Any]
    project = get_project(name)
    compose_file = Path(project["compose_file"]) if project.get("compose_file") else None
    env_file = Path(project["env_file"]) if project.get("env_file") else None
    compose_yaml = ""
    env_text = ""
    if compose_file and compose_file.is_file():
        compose_yaml = compose_file.read_text(encoding="utf-8")
    if env_file and env_file.is_file():
        env_text = env_file.read_text(encoding="utf-8")
    result = dict(project)
    result["compose_yaml"] = compose_yaml
    result["env_text"] = env_text
    return result


def destroy(name, remove_files=False):
    # type: (str, bool) -> Dict[str, Any]
    project = store.get_project(_validate_name(name))
    if not project:
        raise AppError("项目不存在: {}".format(name))
    try:
        from .docker import compose_cwd, compose_prefix
        from .util import run

        run(compose_prefix(project) + ["down", "--remove-orphans"], cwd=compose_cwd(project), check=False)
    except AppError:
        pass
    unregister(name)
    if remove_files and project.get("managed"):
        shutil.rmtree(project["workdir"], ignore_errors=True)
    return {"removed": name}


def _require_registered(name):
    # type: (str) -> Dict[str, Any]
    project = store.get_project(_validate_name(name))
    if project:
        return project
    raise AppError("请先登记项目再执行操作: {}".format(name))


def lifecycle(name, action, service=None, stream=False):
    # type: (str, str, Optional[str], bool) -> Union[Dict[str, Any], int]
    project = _require_registered(name)
    from .docker import compose_cwd, compose_prefix
    from .util import run

    args = compose_prefix(project)
    if action == "up":
        args += ["up", "-d", "--remove-orphans"]
    elif action == "down":
        args += ["down", "--remove-orphans"]
    elif action == "restart":
        args += ["restart"]
    elif action == "pull":
        args += ["pull"]
    elif action == "stop":
        args += ["stop"]
    elif action == "start":
        args += ["start"]
    else:
        raise AppError("未知操作: {}".format(action))
    if service and action in ("restart", "stop", "start", "pull"):
        args.append(service)
    elif service and action == "up":
        args.append(service)

    cwd = compose_cwd(project)
    if stream:
        return stream_cmd(args, cwd=cwd)
    proc = run(args, cwd=cwd, check=False, timeout=600)
    if proc.returncode != 0:
        raise AppError((proc.stderr or proc.stdout or "").strip() or "{} 失败".format(action))
    return _enrich(project)


def scan(max_depth=4):
    # type: (int) -> List[Dict[str, Any]]
    found = []  # type: List[Dict[str, Any]]
    registered_files = set(p.get("compose_file") for p in store.load_projects())

    def walk(root, depth):
        # type: (Path, int) -> None
        if depth > max_depth or not root.is_dir():
            return
        try:
            entries = list(root.iterdir())
        except OSError:
            return
        for entry in entries:
            name = entry.name
            if entry.is_dir():
                if name in paths.SKIP_DIR_NAMES or name.startswith("."):
                    continue
                walk(entry, depth + 1)
                continue
            if name in paths.COMPOSE_FILENAMES:
                compose_file = str(entry.resolve()) if entry.exists() else str(entry)
                found.append(
                    {
                        "name": entry.parent.name,
                        "compose_file": compose_file,
                        "workdir": str(entry.parent),
                        "registered": compose_file in registered_files,
                    }
                )

    for root in paths.SCAN_ROOTS:
        if root.exists():
            walk(root, 1)
    uniq = {}  # type: Dict[str, Dict[str, Any]]
    for item in found:
        uniq[item["compose_file"]] = item
    return list(uniq.values())
