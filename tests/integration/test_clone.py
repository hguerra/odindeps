"""Offline integration coverage for Git clone snapshots."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "odindeps"


def git(directory: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=directory, check=True, capture_output=True, text=True)


class CloneTests(unittest.TestCase):
    def test_sync_clones_a_tagged_offline_fixture_without_git_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            source.mkdir()
            git(source, "init")
            git(source, "config", "user.email", "test@example.invalid")
            git(source, "config", "user.name", "Test")
            source.joinpath("library.odin").write_text("package library\n", encoding="utf-8")
            git(source, "add", ".")
            git(source, "commit", "-m", "fixture")
            git(source, "tag", "v1")
            bare = root / "remote.git"
            subprocess.run(
                ["git", "clone", "--bare", str(source), str(bare)], check=True, capture_output=True, text=True
            )
            project = root / "project"
            project.mkdir()
            project.joinpath("odindeps.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "dependencies": {"library": {"git": "example.test/team/library", "rev": "v1"}},
                    }
                ),
                encoding="utf-8",
            )
            config = root / "gitconfig"
            config.write_text(
                f'[url "{bare.as_uri()}"]\n\tinsteadOf = https://example.test/team/library.git\n',
                encoding="utf-8",
            )
            environment = {**os.environ, "GIT_CONFIG_GLOBAL": str(config), "GIT_TERMINAL_PROMPT": "0"}

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "sync"], cwd=project, env=environment, capture_output=True, text=True
            )
            destination = project / "third_party" / "library"
            second = subprocess.run(
                [sys.executable, str(SCRIPT), "sync"], cwd=project, env=environment, capture_output=True, text=True
            )
            metadata = json.loads(destination.joinpath(".odindeps-meta.json").read_text(encoding="utf-8"))

            self.assertTrue(destination.joinpath("library.odin").is_file())
            self.assertFalse(destination.joinpath(".git").exists())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(metadata["rev"], "v1")
        self.assertEqual(len(metadata["commit"]), 40)

    @unittest.skipIf(sys.platform.startswith("win"), "native Windows does not support cache symlinks")
    def test_sync_reuses_an_immutable_cache_snapshot_and_relinks_without_deleting_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            source.mkdir()
            git(source, "init")
            git(source, "config", "user.email", "test@example.invalid")
            git(source, "config", "user.name", "Test")
            source.joinpath("library.odin").write_text("package library\n", encoding="utf-8")
            git(source, "add", ".")
            git(source, "commit", "-m", "fixture")
            bare = root / "remote.git"
            subprocess.run(
                ["git", "clone", "--bare", str(source), str(bare)], check=True, capture_output=True, text=True
            )
            cache = root / "cache"
            config = root / "gitconfig"
            config.write_text(
                f'[url "{bare.as_uri()}"]\n\tinsteadOf = https://example.test/team/library.git\n',
                encoding="utf-8",
            )
            environment = {**os.environ, "GIT_CONFIG_GLOBAL": str(config), "GIT_TERMINAL_PROMPT": "0"}
            manifest = {
                "schema_version": 1,
                "dependencies": {
                    "library": {
                        "git": "example.test/team/library",
                        "rev": "HEAD",
                        "options": {"cache": {"mode": "symlink", "directory": str(cache)}},
                    }
                },
            }
            projects = []
            for name in ("one", "two"):
                project = root / name
                project.mkdir()
                project.joinpath("odindeps.json").write_text(json.dumps(manifest), encoding="utf-8")
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "sync"], cwd=project, env=environment, capture_output=True, text=True
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                projects.append(project / "third_party" / "library")
            entries = list(cache.iterdir())
            entry_count = len(entries)
            links_are_present = all(project.is_symlink() for project in projects)

        self.assertEqual(entry_count, 1)
        self.assertTrue(links_are_present)


if __name__ == "__main__":
    unittest.main()
