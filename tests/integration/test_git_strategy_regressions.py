"""Offline integration regressions for Git-managed strategies."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "odindeps"


def git(directory: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=directory,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def git_subtree_is_available() -> bool:
    completed = subprocess.run(
        ["git", "subtree"],
        check=False,
        capture_output=True,
        text=True,
    )
    return "is not a git command" not in f"{completed.stdout}\n{completed.stderr}"


def create_fixture(root: Path) -> tuple[Path, str]:
    source = root / "source"
    source.mkdir()
    git(source, "init")
    git(source, "config", "user.email", "test@example.invalid")
    git(source, "config", "user.name", "Test")
    source.joinpath("library.odin").write_text("package library\n", encoding="utf-8")
    git(source, "add", ".")
    git(source, "commit", "-m", "fixture")
    commit = git(source, "rev-parse", "HEAD")
    git(source, "tag", "v1")
    bare = root / "remote.git"
    subprocess.run(
        ["git", "clone", "--bare", str(source), str(bare)],
        check=True,
        capture_output=True,
        text=True,
    )
    return bare, commit


def configure_environment(root: Path, bare: Path) -> dict[str, str]:
    config = root / "gitconfig"
    config.write_text(
        "\n".join(
            (
                f'[url "file://{bare}"]',
                "\tinsteadOf = https://example.test/team/library.git",
                '[protocol "file"]',
                "\tallow = always",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        **os.environ,
        "GIT_CONFIG_GLOBAL": str(config),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }


def initialize_project(root: Path, strategy: str) -> Path:
    project = root / "project"
    project.mkdir()
    git(project, "init")
    git(project, "config", "user.email", "test@example.invalid")
    git(project, "config", "user.name", "Test")
    project.joinpath("odindeps.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dependencies": {
                    "library": {
                        "git": "example.test/team/library",
                        "rev": "v1",
                        "options": {"git": {"strategy": strategy}},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    git(project, "add", "odindeps.json")
    git(project, "commit", "-m", "manifest")
    return project


def run_sync(
    project: Path,
    environment: dict[str, str],
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "sync", *arguments],
        cwd=project,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


class GitStrategyRegressionTests(unittest.TestCase):
    def test_sync_materializes_multiple_submodules_in_one_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bare, expected_commit = create_fixture(root)
            environment = configure_environment(root, bare)
            project = initialize_project(root, "submodule")
            project.joinpath("odindeps.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "dependencies": {
                            name: {
                                "git": "example.test/team/library",
                                "rev": "v1",
                                "options": {"git": {"strategy": "submodule"}},
                            }
                            for name in ("first", "second")
                        },
                    }
                ),
                encoding="utf-8",
            )
            git(project, "add", "odindeps.json")
            git(project, "commit", "-m", "declare two submodules")

            result = run_sync(project, environment)

            self.assertEqual(result.returncode, 0, result.stderr)
            for name in ("first", "second"):
                with self.subTest(name=name):
                    destination = project / "third_party" / name
                    self.assertEqual(git(destination, "rev-parse", "HEAD"), expected_commit)
            self.assertIn("third_party/first", project.joinpath(".gitmodules").read_text(encoding="utf-8"))
            self.assertIn("third_party/second", project.joinpath(".gitmodules").read_text(encoding="utf-8"))

    @unittest.skipUnless(git_subtree_is_available(), "git subtree is unavailable")
    def test_sync_orders_subtree_before_clone_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bare, _ = create_fixture(root)
            environment = configure_environment(root, bare)
            project = initialize_project(root, "clone")
            project.joinpath("odindeps.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "dependencies": {
                            "first_clone": {
                                "git": "example.test/team/library",
                                "rev": "v1",
                            },
                            "second_subtree": {
                                "git": "example.test/team/library",
                                "rev": "v1",
                                "options": {"git": {"strategy": "subtree"}},
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            git(project, "add", "odindeps.json")
            git(project, "commit", "-m", "declare mixed strategies")

            result = run_sync(project, environment)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(project.joinpath("third_party/first_clone/library.odin").is_file())
            self.assertTrue(project.joinpath("third_party/second_subtree/library.odin").is_file())

    def test_forced_submodule_refresh_is_idempotent_and_preserves_the_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bare, expected_commit = create_fixture(root)
            environment = configure_environment(root, bare)
            project = initialize_project(root, "submodule")
            destination = project / "third_party" / "library"
            first = run_sync(project, environment)
            self.assertEqual(first.returncode, 0, first.stderr)
            git(project, "commit", "-m", "materialize submodule")

            forced = run_sync(project, environment, "--force")

            self.assertTrue(destination.is_dir())
            self.assertEqual(git(destination, "rev-parse", "HEAD"), expected_commit)
        self.assertEqual(forced.returncode, 0, forced.stderr)

    @unittest.skipUnless(git_subtree_is_available(), "git subtree is unavailable")
    def test_unchanged_subtree_sync_remains_idempotent_after_unrelated_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bare, _ = create_fixture(root)
            environment = configure_environment(root, bare)
            project = initialize_project(root, "subtree")
            first = run_sync(project, environment)
            self.assertEqual(first.returncode, 0, first.stderr)
            project.joinpath("README.md").write_text("# Consumer\n", encoding="utf-8")
            git(project, "add", "README.md")
            git(project, "commit", "-m", "document consumer")
            first_head = git(project, "rev-parse", "HEAD")

            second = run_sync(project, environment)

            self.assertEqual(git(project, "rev-parse", "HEAD"), first_head)
        self.assertEqual(second.returncode, 0, second.stderr)

    @unittest.skipUnless(git_subtree_is_available(), "git subtree is unavailable")
    def test_forced_subtree_sync_rejects_an_unowned_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bare, _ = create_fixture(root)
            environment = configure_environment(root, bare)
            project = initialize_project(root, "subtree")
            destination = project / "third_party" / "library"
            destination.mkdir(parents=True)
            destination.joinpath("local.odin").write_text("package library\n", encoding="utf-8")
            git(project, "add", "third_party")
            git(project, "commit", "-m", "add local library")
            head = git(project, "rev-parse", "HEAD")

            forced = run_sync(project, environment, "--force")

            self.assertEqual(forced.returncode, 3, forced.stderr)
            self.assertIn("subtree is not managed", forced.stderr)
            self.assertEqual(git(project, "rev-parse", "HEAD"), head)
            self.assertEqual(
                destination.joinpath("local.odin").read_text(encoding="utf-8"),
                "package library\n",
            )

    @unittest.skipUnless(git_subtree_is_available(), "git subtree is unavailable")
    def test_forced_subtree_sync_accepts_an_owned_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bare, _ = create_fixture(root)
            environment = configure_environment(root, bare)
            project = initialize_project(root, "subtree")
            first = run_sync(project, environment)
            self.assertEqual(first.returncode, 0, first.stderr)

            forced = run_sync(project, environment, "--force")

            self.assertEqual(forced.returncode, 0, forced.stderr)
            self.assertTrue(project.joinpath("third_party/library/library.odin").is_file())


if __name__ == "__main__":
    unittest.main()
