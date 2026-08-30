import argparse
import json
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional

from . import __version__, certs, docker, logs, paths, projects, store
from .errors import AppError
from .util import read_payload


def _ok(data):
    # type: (Any) -> int
    json.dump({"ok": True, "data": data}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def _fail(message, code=1):
    # type: (str, int) -> int
    json.dump({"ok": False, "error": message, "code": code}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return code


def cmd_health(_args, _payload):
    # type: (argparse.Namespace, Dict[str, Any]) -> int
    info = docker.engine_info()
    return _ok(
        {
            "version": __version__,
            "state_dir": str(paths.STATE_DIR),
            "engine": info,
            "projects": len(store.load_projects()),
            "certs": len(certs.list_certs()),
        }
    )


def cmd_projects_list(_args, _payload):
    # type: (argparse.Namespace, Dict[str, Any]) -> int
    return _ok(projects.list_projects())


def cmd_projects_get(args, _payload):
    # type: (argparse.Namespace, Dict[str, Any]) -> int
    return _ok(projects.read_files(args.name))


def cmd_projects_register(_args, payload):
    # type: (argparse.Namespace, Dict[str, Any]) -> int
    return _ok(projects.register(payload))


def cmd_projects_create(_args, payload):
    # type: (argparse.Namespace, Dict[str, Any]) -> int
    return _ok(projects.create(payload))


def cmd_projects_update(args, payload):
    # type: (argparse.Namespace, Dict[str, Any]) -> int
    return _ok(projects.update_compose(args.name, payload))


def cmd_projects_unregister(args, payload):
    # type: (argparse.Namespace, Dict[str, Any]) -> int
    if payload.get("destroy"):
        return _ok(projects.destroy(args.name, remove_files=bool(payload.get("remove_files"))))
    return _ok(projects.unregister(args.name))


def cmd_projects_scan(_args, payload):
    # type: (argparse.Namespace, Dict[str, Any]) -> int
    return _ok(projects.scan(max_depth=int(payload.get("max_depth") or 4)))


def cmd_projects_action(args, payload):
    # type: (argparse.Namespace, Dict[str, Any]) -> int
    stream = bool(args.stream or payload.get("stream"))
    result = projects.lifecycle(
        args.name,
        args.action,
        service=args.service or payload.get("service"),
        stream=stream,
    )
    if stream:
        return int(result) if isinstance(result, int) else 0
    return _ok(result)


def cmd_certs_list(_args, _payload):
    # type: (argparse.Namespace, Dict[str, Any]) -> int
    return _ok(certs.list_certs())


def cmd_certs_get(args, payload):
    # type: (argparse.Namespace, Dict[str, Any]) -> int
    return _ok(certs.get_cert(args.name, include_pem=bool(payload.get("include_pem"))))


def cmd_certs_import(_args, payload):
    # type: (argparse.Namespace, Dict[str, Any]) -> int
    return _ok(certs.import_cert(payload))


def cmd_certs_generate(_args, payload):
    # type: (argparse.Namespace, Dict[str, Any]) -> int
    return _ok(certs.generate(payload))


def cmd_certs_delete(args, _payload):
    # type: (argparse.Namespace, Dict[str, Any]) -> int
    return _ok(certs.delete(args.name))


def cmd_certs_assign(args, payload):
    # type: (argparse.Namespace, Dict[str, Any]) -> int
    return _ok(
        certs.assign(
            args.name,
            payload.get("project") or args.project,
            unassign=bool(payload.get("unassign") or args.unassign),
        )
    )


def cmd_logs_tail(args, payload):
    # type: (argparse.Namespace, Dict[str, Any]) -> int
    text = logs.tail(
        args.name,
        service=args.service or payload.get("service"),
        lines=int(args.lines or payload.get("lines") or 200),
        timestamps=not payload.get("no_timestamps"),
    )
    if args.stream:
        sys.stdout.write(text)
        return 0
    return _ok({"text": text})


def cmd_logs_follow(args, payload):
    # type: (argparse.Namespace, Dict[str, Any]) -> int
    return logs.follow(
        args.name,
        service=args.service or payload.get("service"),
        lines=int(args.lines or payload.get("lines") or 200),
        timestamps=not payload.get("no_timestamps"),
    )


COMMANDS = {
    "health": cmd_health,
    "projects.list": cmd_projects_list,
    "projects.get": cmd_projects_get,
    "projects.register": cmd_projects_register,
    "projects.create": cmd_projects_create,
    "projects.update": cmd_projects_update,
    "projects.unregister": cmd_projects_unregister,
    "projects.scan": cmd_projects_scan,
    "projects.up": cmd_projects_action,
    "projects.down": cmd_projects_action,
    "projects.restart": cmd_projects_action,
    "projects.pull": cmd_projects_action,
    "projects.start": cmd_projects_action,
    "projects.stop": cmd_projects_action,
    "certs.list": cmd_certs_list,
    "certs.get": cmd_certs_get,
    "certs.import": cmd_certs_import,
    "certs.generate": cmd_certs_generate,
    "certs.delete": cmd_certs_delete,
    "certs.assign": cmd_certs_assign,
    "logs.tail": cmd_logs_tail,
    "logs.follow": cmd_logs_follow,
}  # type: Dict[str, Callable[[argparse.Namespace, Dict[str, Any]], int]]


def build_parser():
    # type: () -> argparse.ArgumentParser
    parser = argparse.ArgumentParser(prog="dock-panel", description="Dock Panel Cockpit 后端")
    parser.add_argument("command", help="例如 projects.list / certs.generate")
    parser.add_argument("--name", help="项目或证书名称")
    parser.add_argument("--project", help="关联项目名称")
    parser.add_argument("--service", help="Compose 服务名")
    parser.add_argument("--lines", type=int, default=200)
    parser.add_argument("--stream", action="store_true", help="原始流式输出，不包 JSON")
    parser.add_argument("--unassign", action="store_true")
    parser.add_argument("--payload", help="JSON 载荷（调试用，默认读 stdin）")
    return parser


def main(argv=None):
    # type: (Optional[List[str]]) -> int
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command in (
        "projects.up",
        "projects.down",
        "projects.restart",
        "projects.pull",
        "projects.start",
        "projects.stop",
    ):
        args.action = args.command.split(".", 1)[1]
    handler = COMMANDS.get(args.command)
    if handler is None:
        return _fail("未知命令: {}".format(args.command))
    try:
        payload = json.loads(args.payload) if args.payload else read_payload()
        if not isinstance(payload, dict):
            raise AppError("payload 必须是 JSON 对象")
        paths.ensure_dirs()
        return handler(args, payload)
    except AppError as exc:
        if args.stream:
            sys.stderr.write(exc.message + "\n")
            return exc.code
        return _fail(exc.message, exc.code)
    except BrokenPipeError:
        return 0
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        if args.stream:
            return 1
        return _fail(str(exc), 1)


if __name__ == "__main__":
    sys.exit(main())
