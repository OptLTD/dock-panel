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

    def test_read_compose_project_name(self):
        compose = paths.MANAGED_DIR / "sample-compose.yaml"
        paths.MANAGED_DIR.mkdir(parents=True, exist_ok=True)
        compose.write_text(
            "# comment\nname: duolali-prod\n\nservices:\n  app:\n    image: nginx\n",
            encoding="utf-8",
        )
        self.assertEqual(projects.read_compose_project_name(compose), "duolali-prod")

    def test_compose_prefix_uses_project_directory(self):
        from src import docker as docker_mod

        docker_mod._flavor_cache = "docker"
        args = docker_mod.compose_prefix(
            {
                "name": "duolali-prod",
                "compose_file": "/data/compose.prod.yaml",
                "workdir": "/data",
            }
        )
        self.assertIn("--project-directory", args)
        self.assertEqual(args[args.index("--project-directory") + 1], "/data")
        self.assertEqual(args[args.index("-p") + 1], "duolali-prod")

    def test_compose_prefix_podman_skips_project_directory(self):
        from src import docker as docker_mod

        docker_mod._flavor_cache = "podman"
        args = docker_mod.compose_prefix(
            {
                "name": "duolali-prod",
                "compose_file": "/data/compose.yaml",
                "workdir": "/data",
            }
        )
        self.assertNotIn("--project-directory", args)
        self.assertEqual(args[:2], ["docker", "compose"])
        self.assertIn("-f", args)
        self.assertIn("/data/compose.yaml", args)

    def test_normalize_and_label_fallback_shape(self):
        from src.docker import _normalize_container

        row = _normalize_container(
            {
                "ID": "abc",
                "Names": "/duolali-prod",
                "Image": "optltd/duolali:latest",
                "State": "running",
                "Status": "Up 2 hours",
                "Ports": "0.0.0.0:80->80/tcp,0.0.0.0:443->443/tcp",
                "Labels": "com.docker.compose.project=duolali-prod,com.docker.compose.service=duolali-prod",
            }
        )
        self.assertEqual(row["Name"], "duolali-prod")
        self.assertEqual(row["State"], "running")
        self.assertEqual(row["Service"], "duolali-prod")
        self.assertEqual(len(row["Publishers"]), 2)
        status = projects._status_from_ps([row])
        self.assertEqual(status["summary"], "running")
        self.assertEqual(status["running"], 1)
        self.assertEqual(status["total"], 1)

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
