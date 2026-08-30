import json
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import paths, store
from .errors import AppError
from .util import run, slugify


def _now():
    # type: () -> str
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cert_dir(name):
    # type: (str) -> Path
    return paths.CERTS_DIR / slugify(name)


def _parse_openssl_date(value):
    # type: (str) -> Optional[datetime]
    value = value.strip()
    for fmt in ("%b %d %H:%M:%S %Y %Z", "%b  %d %H:%M:%S %Y %Z"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def inspect_pem(cert_pem):
    # type: (str) -> Dict[str, Any]
    proc = run(
        ["openssl", "x509", "-noout", "-subject", "-issuer", "-dates", "-fingerprint", "-sha256"],
        stdin=cert_pem,
        check=False,
    )
    if proc.returncode != 0:
        raise AppError((proc.stderr or "无法解析证书").strip())
    info = {
        "subject": "",
        "issuer": "",
        "not_before": "",
        "not_after": "",
        "fingerprint": "",
        "sans": [],
        "days_left": None,
        "expired": False,
        "self_signed": False,
    }  # type: Dict[str, Any]
    for line in proc.stdout.splitlines():
        if line.startswith("subject="):
            info["subject"] = line.split("=", 1)[1].strip()
        elif line.startswith("issuer="):
            info["issuer"] = line.split("=", 1)[1].strip()
        elif line.startswith("notBefore="):
            info["not_before"] = line.split("=", 1)[1].strip()
        elif line.startswith("notAfter="):
            info["not_after"] = line.split("=", 1)[1].strip()
        elif "Fingerprint=" in line:
            info["fingerprint"] = line.split("=", 1)[1].strip()

    san_proc = run(
        ["openssl", "x509", "-noout", "-text"],
        stdin=cert_pem,
        check=False,
    )
    sans = []  # type: List[str]
    if san_proc.returncode == 0:
        for match in re.finditer(r"(?:DNS|IP Address|IP):([^,\n]+)", san_proc.stdout):
            sans.append(match.group(1).strip())
    info["sans"] = sans
    info["self_signed"] = info["subject"] == info["issuer"]

    expiry = _parse_openssl_date(info["not_after"]) if info["not_after"] else None
    if expiry:
        delta = expiry - datetime.now(timezone.utc)
        info["days_left"] = delta.days
        info["expired"] = delta.total_seconds() < 0
        info["not_after_iso"] = expiry.strftime("%Y-%m-%dT%H:%M:%SZ")
    return info


def list_certs():
    # type: () -> List[Dict[str, Any]]
    paths.ensure_dirs()
    items = []  # type: List[Dict[str, Any]]
    entries = sorted(paths.CERTS_DIR.iterdir()) if paths.CERTS_DIR.exists() else []
    for entry in entries:
        if not entry.is_dir():
            continue
        cert_file = entry / "cert.pem"
        meta_file = entry / "meta.json"
        if not cert_file.is_file():
            continue
        meta = {}  # type: Dict[str, Any]
        if meta_file.is_file():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except ValueError:
                meta = {}
        try:
            parsed = inspect_pem(cert_file.read_text(encoding="utf-8"))
        except AppError as exc:
            parsed = {"error": exc.message}
        row = {
            "name": entry.name,
            "path": str(cert_file),
            "key_path": str(entry / "key.pem"),
            "has_key": (entry / "key.pem").is_file(),
        }
        row.update(meta)
        row.update(parsed)
        items.append(row)
    return items


def get_cert(name, include_pem=False):
    # type: (str, bool) -> Dict[str, Any]
    directory = _cert_dir(name)
    cert_file = directory / "cert.pem"
    if not cert_file.is_file():
        raise AppError("证书不存在: {}".format(name))
    pem = cert_file.read_text(encoding="utf-8")
    meta = {}  # type: Dict[str, Any]
    meta_file = directory / "meta.json"
    if meta_file.is_file():
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    data = {
        "name": directory.name,
        "path": str(cert_file),
        "key_path": str(directory / "key.pem"),
        "has_key": (directory / "key.pem").is_file(),
    }
    data.update(meta)
    data.update(inspect_pem(pem))
    if include_pem:
        data["cert_pem"] = pem
    return data


def import_cert(payload):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    name = slugify(payload.get("name") or "")
    cert_pem = str(payload.get("cert_pem") or "").strip()
    key_pem = str(payload.get("key_pem") or "").strip()
    chain_pem = str(payload.get("chain_pem") or "").strip()
    if not cert_pem:
        raise AppError("缺少 cert_pem")
    inspect_pem(cert_pem)
    directory = _cert_dir(name)
    if directory.exists() and not payload.get("overwrite"):
        raise AppError("证书已存在: {}".format(name))
    directory.mkdir(parents=True, exist_ok=True)
    fullchain = cert_pem if not chain_pem else cert_pem.rstrip() + "\n" + chain_pem.strip() + "\n"
    (directory / "cert.pem").write_text(
        fullchain if fullchain.endswith("\n") else fullchain + "\n",
        encoding="utf-8",
    )
    if key_pem:
        key_path = directory / "key.pem"
        key_path.write_text(key_pem if key_pem.endswith("\n") else key_pem + "\n", encoding="utf-8")
        key_path.chmod(0o600)
    meta = {
        "source": payload.get("source") or "upload",
        "notes": payload.get("notes") or "",
        "created_at": _now(),
        "updated_at": _now(),
    }
    (directory / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return get_cert(name)


def generate(payload):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    name = slugify(payload.get("name") or "")
    cn = str(payload.get("cn") or name).strip()
    days = int(payload.get("days") or 365)
    if days < 1 or days > 3650:
        raise AppError("有效期必须在 1–3650 天之间")
    sans = payload.get("sans") or []
    if isinstance(sans, str):
        sans = [item.strip() for item in re.split(r"[,\n]", sans) if item.strip()]
    san_parts = []  # type: List[str]
    for item in [cn] + list(sans):
        item = str(item).strip()
        if not item:
            continue
        if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", item):
            san_parts.append("IP:{}".format(item))
        else:
            san_parts.append("DNS:{}".format(item))
    # de-duplicate while keeping order
    uniq = []  # type: List[str]
    seen = set()
    for part in san_parts:
        if part not in seen:
            seen.add(part)
            uniq.append(part)
    san_parts = uniq

    directory = _cert_dir(name)
    if directory.exists() and not payload.get("overwrite"):
        raise AppError("证书已存在: {}".format(name))
    directory.mkdir(parents=True, exist_ok=True)
    cert_file = directory / "cert.pem"
    key_file = directory / "key.pem"

    # OpenSSL 1.0.x (CentOS 7) 不支持 -addext，改用临时配置文件
    conf = tempfile.NamedTemporaryFile("w", suffix=".cnf", delete=False)
    try:
        conf.write("[req]\n")
        conf.write("distinguished_name = req_distinguished_name\n")
        conf.write("x509_extensions = v3_req\n")
        conf.write("prompt = no\n")
        conf.write("[req_distinguished_name]\n")
        conf.write("CN = {}\n".format(cn))
        conf.write("[v3_req]\n")
        conf.write("basicConstraints = CA:FALSE\n")
        conf.write("keyUsage = digitalSignature, keyEncipherment\n")
        conf.write("extendedKeyUsage = serverAuth\n")
        if san_parts:
            conf.write("subjectAltName = {}\n".format(",".join(san_parts)))
        conf.flush()
        conf.close()
        run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-sha256",
                "-days",
                str(days),
                "-nodes",
                "-keyout",
                str(key_file),
                "-out",
                str(cert_file),
                "-config",
                conf.name,
            ]
        )
    finally:
        try:
            Path(conf.name).unlink()
        except OSError:
            pass

    key_file.chmod(0o600)
    meta = {
        "source": "self-signed",
        "notes": payload.get("notes") or "",
        "cn": cn,
        "days": days,
        "created_at": _now(),
        "updated_at": _now(),
    }
    (directory / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return get_cert(name)


def delete(name):
    # type: (str) -> Dict[str, Any]
    directory = _cert_dir(name)
    if not directory.exists():
        raise AppError("证书不存在: {}".format(name))
    with store.locked_projects() as items:
        for item in items:
            certs_list = item.get("certs") or []
            item["certs"] = [c for c in certs_list if c != directory.name]
    shutil.rmtree(directory)
    return {"removed": directory.name}


def assign(cert_name, project_name, unassign=False):
    # type: (str, str, bool) -> Dict[str, Any]
    cert = get_cert(cert_name)
    from . import projects as project_mod

    project = store.get_project(project_name)
    if not project:
        raise AppError("项目不存在: {}".format(project_name))
    certs_list = list(project.get("certs") or [])  # type: List[str]
    name = cert["name"]
    if unassign:
        certs_list = [c for c in certs_list if c != name]
    elif name not in certs_list:
        certs_list.append(name)
    project["certs"] = certs_list
    project["updated_at"] = _now()

    target = Path(project["workdir"]) / "certs" / name if project.get("workdir") else None
    if unassign and target and target.exists():
        shutil.rmtree(str(target), ignore_errors=True)
    elif not unassign and target is not None:
        target.mkdir(parents=True, exist_ok=True)
        src = _cert_dir(name)
        for filename in ("cert.pem", "key.pem"):
            source = src / filename
            if source.is_file():
                dest = target / filename
                if dest.exists() or dest.is_symlink():
                    dest.unlink()
                dest.symlink_to(source)

    with store.locked_projects() as items:
        for index, item in enumerate(items):
            if item["name"] == project_name:
                items[index] = project
                break
    return {"project": project_mod.get_project(project_name), "cert": cert}
