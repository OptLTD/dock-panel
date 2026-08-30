#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import certs, paths, projects, store
from src.cli import main as cli_main
from src.errors import AppError


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        paths.STATE_DIR = root
        paths.PROJECTS_FILE = root / "projects.json"
        paths.CERTS_DIR = root / "certs"
        paths.MANAGED_DIR = root / "projects"
        paths.ensure_dirs()

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_and_list_managed_project(self):
        created = projects.create(
            {
                "name": "web",
                "compose_yaml": "services:\n  nginx:\n    image: nginx:alpine\n",
            }
        )
        self.assertTrue(created["managed"])
        self.assertTrue(Path(created["compose_file"]).is_file())
        listed = store.load_projects()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["name"], "web")

    def test_register_requires_file(self):
        with self.assertRaises(AppError):
            projects.register({"name": "missing", "compose_file": "/no/such/compose.yaml"})

    def test_slug_and_render(self):
        yaml_text = projects.render_compose(
            [{"name": "api", "image": "ghcr.io/example/api:1", "ports": ["8080:80"], "environment": {"A": "b c"}}],
            project_name="demo",
        )
        self.assertIn("image: ghcr.io/example/api:1", yaml_text)
        self.assertIn('A: "b c"', yaml_text)

    def test_cli_health_json(self):
        with mock.patch(
            "src.docker.engine_info",
            return_value={
                "docker": False,
                "compose": False,
                "version": None,
                "compose_version": None,
                "error": "no",
            },
        ):
            rc = cli_main(["health", "--payload", "{}"])
        self.assertEqual(rc, 0)


class CertTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        paths.STATE_DIR = root
        paths.PROJECTS_FILE = root / "projects.json"
        paths.CERTS_DIR = root / "certs"
        paths.MANAGED_DIR = root / "projects"
        paths.ensure_dirs()

    def tearDown(self):
        self.tmp.cleanup()

    def test_inspect_rejects_garbage(self):
        with self.assertRaises(AppError):
            certs.inspect_pem("not-a-cert")


if __name__ == "__main__":
    os.chdir(str(Path(__file__).resolve().parents[1]))
    unittest.main()
