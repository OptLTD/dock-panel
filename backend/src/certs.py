from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import paths, store
from .errors import AppError
from .util import run, slugify


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cert_dir(name: str) -> Path:
    return paths.CERTS_DIR / slugify(name)


def _parse_openssl_date(value: str) -> datetime | None:
    value = value.strip()
    for fmt in ("%b %d %H:%M:%S %Y %Z", "%b  %d %H:%M:%S %Y %Z"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def inspect_pem(cert_pem: str) -> dict[str, Any]:
    proc = run(
        ["openssl", "x509", "-noout", "-subject", "-issuer", "-dates", "-fingerprint", "-sha256"],
        stdin=cert_pem,
        check=False,
    )
    if proc.returncode != 0:
        raise AppError((proc.stderr or "无法解析证书").strip())
    info: dict[str, Any] = {
        "subject": "",
        "issuer": "",
        "not_before": "",
        "not_after": "",
        "fingerprint": "",
        "sans": [],
        "days_left": None,
        "expired": False,
        "self_signed": False,
    }
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
        ["openssl", "x509", "-noout", "-ext", "subjectAltName"],
        stdin=cert_pem,
        check=False,
    )
    sans: list[str] = []
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


def list_certs() -> list[dict[str, Any]]:
    paths.ensure_dirs()
    items: list[dict[str, Any]] = []
    for entry in sorted(paths.CERTS_DIR.iterdir()) if paths.CERTS_DIR.exists() else []:
        if not entry.is_dir():
            continue
        cert_file = entry / "cert.pem"
        meta_file = entry / "meta.json"
        if not cert_file.is_file():
            continue
        meta: dict[str, Any] = {}
        if meta_file.is_file():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                meta = {}
        try:
            parsed = inspect_pem(cert_file.read_text(encoding="utf-8"))
        except AppError as exc:
            parsed = {"error": exc.message}
        items.append(
            {
                "name": entry.name,
                "path": str(cert_file),
                "key_path": str(entry / "key.pem"),
                "has_key": (entry / "key.pem").is_file(),
                **meta,
                **parsed,
            }
        )
    return items


def get_cert(name: str, *, include_pem: bool = False) -> dict[str, Any]:
    directory = _cert_dir(name)
    cert_file = directory / "cert.pem"
    if not cert_file.is_file():
        raise AppError(f"证书不存在: {name}")
    pem = cert_file.read_text(encoding="utf-8")
    meta: dict[str, Any] = {}
    meta_file = directory / "meta.json"
    if meta_file.is_file():
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    data = {
        "name": directory.name,
        "path": str(cert_file),
        "key_path": str(directory / "key.pem"),
        "has_key": (directory / "key.pem").is_file(),
        **meta,
        **inspect_pem(pem),
    }
    if include_pem:
        data["cert_pem"] = pem
    return data


def import_cert(payload: dict[str, Any]) -> dict[str, Any]:
    name = slugify(payload.get("name") or "")
    cert_pem = str(payload.get("cert_pem") or "").strip()
    key_pem = str(payload.get("key_pem") or "").strip()
    chain_pem = str(payload.get("chain_pem") or "").strip()
    if not cert_pem:
        raise AppError("缺少 cert_pem")
    inspect_pem(cert_pem)
    directory = _cert_dir(name)
    if directory.exists() and not payload.get("overwrite"):
        raise AppError(f"证书已存在: {name}")
    directory.mkdir(parents=True, exist_ok=True)
    fullchain = cert_pem if not chain_pem else cert_pem.rstrip() + "\n" + chain_pem.strip() + "\n"
    (directory / "cert.pem").write_text(fullchain if fullchain.endswith("\n") else fullchain + "\n", encoding="utf-8")
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


def generate(payload: dict[str, Any]) -> dict[str, Any]:
    name = slugify(payload.get("name") or "")
    cn = str(payload.get("cn") or name).strip()
    days = int(payload.get("days") or 365)
    if days < 1 or days > 3650:
        raise AppError("有效期必须在 1–3650 天之间")
    sans = payload.get("sans") or []
    if isinstance(sans, str):
        sans = [item.strip() for item in re.split(r"[,\n]", sans) if item.strip()]
    san_parts: list[str] = []
    for item in [cn, *sans]:
        item = str(item).strip()
        if not item:
            continue
        if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", item):
            san_parts.append(f"IP:{item}")
        else:
            san_parts.append(f"DNS:{item}")
    # de-duplicate while keeping order
    san_parts = list(dict.fromkeys(san_parts))
    directory = _cert_dir(name)
    if directory.exists() and not payload.get("overwrite"):
        raise AppError(f"证书已存在: {name}")
    directory.mkdir(parents=True, exist_ok=True)
    cert_file = directory / "cert.pem"
    key_file = directory / "key.pem"
    args = [
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
        "-subj",
        f"/CN={cn}",
    ]
    if san_parts:
        args.extend(["-addext", "subjectAltName=" + ",".join(san_parts)])
    run(args)
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


def delete(name: str) -> dict[str, Any]:
    directory = _cert_dir(name)
    if not directory.exists():
        raise AppError(f"证书不存在: {name}")
    # drop assignments
    with store.locked_projects() as items:
        for item in items:
            certs = item.get("certs") or []
            item["certs"] = [c for c in certs if c != directory.name]
    shutil.rmtree(directory)
    return {"removed": directory.name}


def assign(cert_name: str, project_name: str, *, unassign: bool = False) -> dict[str, Any]:
    cert = get_cert(cert_name)
    from . import projects as project_mod

    project = store.get_project(project_name)
    if not project:
        raise AppError(f"项目不存在: {project_name}")
    certs: list[str] = list(project.get("certs") or [])
    name = cert["name"]
    if unassign:
        certs = [c for c in certs if c != name]
    elif name not in certs:
        certs.append(name)
    project["certs"] = certs
    project["updated_at"] = _now()

    target = Path(project["workdir"]) / "certs" / name if project.get("workdir") else None
    if unassign and target and target.exists():
        shutil.rmtree(target, ignore_errors=True)
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
