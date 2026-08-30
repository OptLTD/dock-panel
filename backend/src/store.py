from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator

from . import paths

try:
    import fcntl
except ImportError:  # pragma: no cover - non-unix
    fcntl = None  # type: ignore[assignment]


@contextmanager
def locked_projects() -> Iterator[list[dict[str, Any]]]:
    paths.ensure_dirs()
    with paths.PROJECTS_FILE.open("a+", encoding="utf-8") as fh:
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        fh.seek(0)
        raw = fh.read().strip()
        data: list[dict[str, Any]] = json.loads(raw) if raw else []
        try:
            yield data
            fh.seek(0)
            fh.truncate()
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            fh.flush()
        finally:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def load_projects() -> list[dict[str, Any]]:
    paths.ensure_dirs()
    raw = paths.PROJECTS_FILE.read_text(encoding="utf-8").strip()
    return json.loads(raw) if raw else []


def get_project(name: str) -> dict[str, Any] | None:
    for item in load_projects():
        if item.get("name") == name:
            return item
    return None
