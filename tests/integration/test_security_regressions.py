"""Offline integration regressions for filesystem and Git trust boundaries."""

from __future__ import annotations

import json
import os
import shlex
import stat
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


def initialize_source(root: Path) -> Path:
    source = root / "source"
    source.mkdir()
    git(source, "init")
    git(source, "config", "user.email", "test@example.invalid")
    git(source, "config", "user.name", "Test")
    return source


def create_bare_remote(root: Path, source: Path) -> Path:
    bare = root / "remote.git"
    subprocess.run(
        ["git", "clone", "--bare", str(source), str(bare)],
        check=True,
        capture_output=True,
        text=True,
    )
    return bare


def write_git_config(path: Path, bare: Path, *, hooks_path: str | None = None) -> None:
    sections = [
        f'[url "file://{bare}"]',
        "\tinsteadOf = https://example.test/team/library.git",
        '[protocol "file"]',
        "\tallow = always",
    ]
    if hooks_path is not None:
        sections.extend(("[core]", f"\thooksPath = {hooks_path}"))
    path.write_text("\n".join(sections) + "\n", encoding="utf-8")


def git_environment(config: Path) -> dict[str, str]:
    return {
        **os.environ,
        "GIT_CONFIG_GLOBAL": str(config),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }


def run_sync(
    project: Path,
    environment: dict[str, str] | None = None,
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


def clone_manifest(
    *,
    rev: str = "v1",
    options: dict[str, object] | None = None,
) -> dict[str, object]:
    dependency: dict[str, object] = {
        "git": "example.test/team/library",
        "rev": rev,
    }
    if options is not None:
        dependency["options"] = options
    return {
        "schema_version": 1,
        "dependencies": {"library": dependency},
    }


class SecurityRegressionTests(unittest.TestCase):
    @unittest.skipIf(sys.platform.startswith("win"), "source symlink attack is POSIX-specific")
    def test_clone_reserved_metadata_symlink_cannot_overwrite_the_project_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = initialize_source(root)
            source.joinpath("library.odin").write_text("package library\n", encoding="utf-8")
            source.joinpath(".odindeps-meta.json").symlink_to("../../../../odindeps.json")
            git(source, "add", ".")
            git(source, "commit", "-m", "malicious metadata symlink")
            git(source, "tag", "v1")
            bare = create_bare_remote(root, source)
            config = root / "gitconfig"
            write_git_config(config, bare)
            environment = git_environment(config)
            project = root / "project"
            project.mkdir()
            manifest = project / "odindeps.json"
            original = json.dumps(clone_manifest()).encode("utf-8")
            manifest.write_bytes(original)

            result = run_sync(project, environment)

            self.assertEqual(manifest.read_bytes(), original)
            self.assertFalse((project / "src" / "third_party" / "library").exists())
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stderr.startswith("odindeps:"), result.stderr)

    @unittest.skipIf(sys.platform.startswith("win"), "source symlink attack is POSIX-specific")
    def test_local_reserved_metadata_symlink_cannot_overwrite_an_outside_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            outside = root / "outside.txt"
            outside.write_text("keep\n", encoding="utf-8")
            source = root / "source"
            source.mkdir()
            source.joinpath("library.odin").write_text("package library\n", encoding="utf-8")
            source.joinpath(".odindeps-meta.json").symlink_to(outside)
            project = root / "project"
            project.mkdir()
            project.joinpath("odindeps.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "dependencies": {"library": {"path": str(source)}},
                    }
                ),
                encoding="utf-8",
            )

            result = run_sync(project)

            self.assertEqual(outside.read_text(encoding="utf-8"), "keep\n")
            self.assertFalse((project / "src" / "third_party" / "library").exists())
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stderr.startswith("odindeps:"), result.stderr)

    @unittest.skipIf(sys.platform.startswith("win"), "dependency hook fixture uses a POSIX shell")
    def test_dependency_post_checkout_hook_is_never_executed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            marker = root / "hook-executed"
            source = initialize_source(root)
            hooks = source / ".githooks"
            hooks.mkdir()
            hook = hooks / "post-checkout"
            hook.write_text(
                f"#!/bin/sh\n: > {shlex.quote(str(marker))}\n",
                encoding="utf-8",
            )
            hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
            source.joinpath("library.odin").write_text("package library\n", encoding="utf-8")
            git(source, "add", ".")
            git(source, "commit", "-m", "dependency with hook")
            git(source, "tag", "v1")
            bare = create_bare_remote(root, source)
            config = root / "gitconfig"
            write_git_config(config, bare, hooks_path=".githooks")
            environment = git_environment(config)
            project = root / "project"
            project.mkdir()
            project.joinpath("odindeps.json").write_text(
                json.dumps(clone_manifest()),
                encoding="utf-8",
            )

            result = run_sync(project, environment)

            self.assertFalse(marker.exists())
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_failed_forced_clone_preserves_the_existing_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = initialize_source(root)
            source.joinpath("library.odin").write_text("package library\n", encoding="utf-8")
            git(source, "add", ".")
            git(source, "commit", "-m", "fixture")
            git(source, "tag", "v1")
            bare = create_bare_remote(root, source)
            config = root / "gitconfig"
            write_git_config(config, bare)
            environment = git_environment(config)
            project = root / "project"
            project.mkdir()
            project.joinpath("odindeps.json").write_text(
                json.dumps(clone_manifest()),
                encoding="utf-8",
            )
            destination = project / "src" / "third_party" / "library"
            first = run_sync(project, environment)
            original_source = destination.joinpath("library.odin").read_bytes()
            original_metadata = destination.joinpath(".odindeps-meta.json").read_bytes()
            bare.rename(root / "remote-offline.git")

            failed = run_sync(project, environment, "--force")

            self.assertTrue(destination.is_dir())
            self.assertEqual(destination.joinpath("library.odin").read_bytes(), original_source)
            self.assertEqual(
                destination.joinpath(".odindeps-meta.json").read_bytes(),
                original_metadata,
            )
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(failed.returncode, 4, failed.stderr)

    def test_mixed_manifest_preflight_prevents_earlier_local_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            local_source = root / "local-source"
            local_source.mkdir()
            local_source.joinpath("local.odin").write_text("package local\n", encoding="utf-8")
            missing_remote = root / "missing.git"
            config = root / "gitconfig"
            write_git_config(config, missing_remote)
            environment = git_environment(config)
            project = root / "project"
            project.mkdir()
            project.joinpath("odindeps.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "dependencies": {
                            "a_local": {"path": str(local_source)},
                            "z_git": {
                                "git": "example.test/team/library",
                                "rev": "v1",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = run_sync(project, environment)

            self.assertFalse((project / "src" / "third_party" / "a_local").exists())
        self.assertEqual(result.returncode, 4, result.stderr)

    @unittest.skipIf(sys.platform.startswith("win"), "native Windows does not support cache symlinks")
    def test_cache_entry_cannot_be_mutated_through_the_project_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = initialize_source(root)
            source.joinpath("library.odin").write_text("package library\n", encoding="utf-8")
            git(source, "add", ".")
            git(source, "commit", "-m", "fixture")
            git(source, "tag", "v1")
            bare = create_bare_remote(root, source)
            config = root / "gitconfig"
            write_git_config(config, bare)
            environment = git_environment(config)
            cache = root / "cache"
            project = root / "project"
            project.mkdir()
            project.joinpath("odindeps.json").write_text(
                json.dumps(
                    clone_manifest(
                        options={
                            "cache": {
                                "mode": "symlink",
                                "directory": str(cache),
                            }
                        }
                    )
                ),
                encoding="utf-8",
            )
            destination = project / "src" / "third_party" / "library"

            result = run_sync(project, environment)

            with self.assertRaises(OSError):
                destination.joinpath("injected.odin").write_text(
                    "package injected\n",
                    encoding="utf-8",
                )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_changed_clone_file_selection_is_an_existing_state_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = initialize_source(root)
            source.joinpath("a.odin").write_text("package a\n", encoding="utf-8")
            source.joinpath("b.odin").write_text("package b\n", encoding="utf-8")
            git(source, "add", ".")
            git(source, "commit", "-m", "fixture")
            git(source, "tag", "v1")
            bare = create_bare_remote(root, source)
            config = root / "gitconfig"
            write_git_config(config, bare)
            environment = git_environment(config)
            project = root / "project"
            project.mkdir()
            manifest = project / "odindeps.json"
            manifest.write_text(
                json.dumps(
                    clone_manifest(
                        options={"git": {"clone": {"files": ["a.odin"]}}}
                    )
                ),
                encoding="utf-8",
            )
            first = run_sync(project, environment)
            manifest.write_text(
                json.dumps(
                    clone_manifest(
                        options={"git": {"clone": {"files": ["b.odin"]}}}
                    )
                ),
                encoding="utf-8",
            )

            second = run_sync(project, environment)

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 3, second.stderr)

    def test_clone_resolves_a_non_default_remote_branch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = initialize_source(root)
            source.joinpath("base.odin").write_text("package base\n", encoding="utf-8")
            git(source, "add", ".")
            git(source, "commit", "-m", "default branch")
            default_branch = git(source, "branch", "--show-current")
            git(source, "switch", "-c", "feature")
            source.joinpath("feature.odin").write_text("package feature\n", encoding="utf-8")
            git(source, "add", ".")
            git(source, "commit", "-m", "feature branch")
            git(source, "switch", default_branch)
            bare = create_bare_remote(root, source)
            config = root / "gitconfig"
            write_git_config(config, bare)
            environment = git_environment(config)
            project = root / "project"
            project.mkdir()
            project.joinpath("odindeps.json").write_text(
                json.dumps(clone_manifest(rev="feature")),
                encoding="utf-8",
            )

            result = run_sync(project, environment)

            self.assertTrue(
                (project / "src" / "third_party" / "library" / "feature.odin").is_file()
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_local_source_path_expands_native_environment_variables(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            source.mkdir()
            source.joinpath("library.odin").write_text("package library\n", encoding="utf-8")
            project = root / "project"
            project.mkdir()
            variable = "ODINDEPS_REGRESSION_LOCAL_SOURCE"
            path_expression = f"%{variable}%" if sys.platform.startswith("win") else f"${variable}"
            project.joinpath("odindeps.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "dependencies": {"library": {"path": path_expression}},
                    }
                ),
                encoding="utf-8",
            )
            environment = {**os.environ, variable: str(source)}

            result = run_sync(project, environment)

            self.assertTrue(
                (project / "src" / "third_party" / "library" / "library.odin").is_file()
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipIf(sys.platform.startswith("win"), "native Windows does not support cache symlinks")
    def test_cache_directory_expands_native_environment_variables(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = initialize_source(root)
            source.joinpath("library.odin").write_text("package library\n", encoding="utf-8")
            git(source, "add", ".")
            git(source, "commit", "-m", "fixture")
            git(source, "tag", "v1")
            bare = create_bare_remote(root, source)
            config = root / "gitconfig"
            write_git_config(config, bare)
            environment = git_environment(config)
            cache = root / "expanded-cache"
            environment["ODINDEPS_REGRESSION_CACHE"] = str(cache)
            project = root / "project"
            project.mkdir()
            project.joinpath("odindeps.json").write_text(
                json.dumps(
                    clone_manifest(
                        options={
                            "cache": {
                                "mode": "symlink",
                                "directory": "$ODINDEPS_REGRESSION_CACHE",
                            }
                        }
                    )
                ),
                encoding="utf-8",
            )

            result = run_sync(project, environment)

            self.assertTrue(cache.is_dir())
            if cache.is_dir():
                self.assertEqual(len(list(cache.iterdir())), 1)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
