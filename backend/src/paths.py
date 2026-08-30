import os
from pathlib import Path

STATE_DIR = Path(os.environ.get("DOCK_PANEL_STATE", "/var/lib/dock-panel"))
PROJECTS_FILE = STATE_DIR / "projects.json"
CERTS_DIR = STATE_DIR / "certs"
MANAGED_DIR = STATE_DIR / "projects"

COMPOSE_FILENAMES = (
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
)

SCAN_ROOTS = (
    Path("/opt"),
    Path("/srv"),
    Path("/home"),
    Path("/root"),
    Path("/data"),
    Path("/var/lib/dock-panel/projects"),
    Path("/etc/compose"),
)

SKIP_DIR_NAMES = {
    "node_modules",
    ".git",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    ".cache",
    "proc",
    "sys",
}


def ensure_dirs():
    # type: () -> None
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    MANAGED_DIR.mkdir(parents=True, exist_ok=True)
    if not PROJECTS_FILE.exists():
        PROJECTS_FILE.write_text("[]\n", encoding="utf-8")
