import json
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from . import paths

try:
    import fcntl
except ImportError:  # pragma: no cover - non-unix
    fcntl = None  # type: ignore


@contextmanager
def locked_projects():
    # type: () -> Iterator[List[Dict[str, Any]]]
    paths.ensure_dirs()
    with paths.PROJECTS_FILE.open("a+", encoding="utf-8") as fh:
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        fh.seek(0)
        raw = fh.read().strip()
        data = json.loads(raw) if raw else []  # type: List[Dict[str, Any]]
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


def load_projects():
    # type: () -> List[Dict[str, Any]]
    paths.ensure_dirs()
    raw = paths.PROJECTS_FILE.read_text(encoding="utf-8").strip()
    return json.loads(raw) if raw else []


def get_project(name):
    # type: (str) -> Optional[Dict[str, Any]]
    for item in load_projects():
        if item.get("name") == name:
            return item
    return None
