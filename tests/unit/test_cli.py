"""Black-box tests for the portable odindeps command-line executable."""

from __future__ import annotations

import json
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "odindeps"


class CliTests(unittest.TestCase):
    def run_cli(self, *arguments: str, script: Path = SCRIPT) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )

    def run_in_directory(self, directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            check=False,
            capture_output=True,
            cwd=directory,
            text=True,
        )

    def test_help_succeeds_and_describes_the_public_commands(self) -> None:
        result = self.run_cli("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: odindeps", result.stdout)
        self.assertIn("init", result.stdout)
        self.assertIn("add", result.stdout)
        self.assertIn("sync", result.stdout)

    def test_add_help_uses_git_and_path_location_flags(self) -> None:
        result = self.run_cli("add", "--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--git", result.stdout)
        self.assertIn("--path", result.stdout)
        self.assertNotIn("--source", result.stdout)
        self.assertNotIn("--local", result.stdout)

    def test_executable_has_the_portable_shebang_and_user_execute_permission(self) -> None:
        self.assertEqual(SCRIPT.read_text(encoding="utf-8").splitlines()[0], "#!/usr/bin/env python3")
        self.assertTrue(SCRIPT.stat().st_mode & stat.S_IXUSR)

    def test_module_load_does_not_run_the_command_line_interface(self) -> None:
        loader = SourceFileLoader("odindeps_under_test", str(SCRIPT))
        specification = spec_from_loader(loader.name, loader)
        self.assertIsNotNone(specification)
        module = module_from_spec(specification)
        sys.modules[loader.name] = module

        loader.exec_module(module)

        self.assertEqual(module.VERSION, "0.1.0")

    def test_version_reports_the_initial_release(self) -> None:
        result = self.run_cli("--version")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "odindeps 0.1.0\n")

    def test_copied_script_runs_without_project_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            copied_script = Path(temporary_directory) / "odindeps"
            shutil.copy2(SCRIPT, copied_script)

            result = self.run_cli("--help", script=copied_script)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: odindeps", result.stdout)

    def test_init_creates_the_exact_minimal_manifest_and_is_byte_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)

            first = self.run_in_directory(directory, "init")
            manifest = directory / "odindeps.json"
            initial_bytes = manifest.read_bytes()
            second = self.run_in_directory(directory, "init")
            final_bytes = manifest.read_bytes()

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(initial_bytes, b'{\n  "schema_version": 1,\n  "dependencies": {}\n}\n')
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(final_bytes, initial_bytes)

    def test_init_refuses_to_overwrite_an_invalid_existing_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            manifest = directory / "odindeps.json"
            invalid_bytes = b"not json\n"
            manifest.write_bytes(invalid_bytes)

            result = self.run_in_directory(directory, "init")

            self.assertEqual(manifest.read_bytes(), invalid_bytes)

        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.startswith("odindeps:"), result.stderr)

    def test_add_path_creates_a_manifest_and_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source = directory / "source"
            source.mkdir()

            result = self.run_in_directory(directory, "add", "--path", str(source), "--name", "shared")
            manifest = (directory / "odindeps.json").read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"shared"', manifest)
        self.assertIn('"path"', manifest)

    def test_add_path_rejects_git_revision_without_mutating_the_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source = directory / "source"
            source.mkdir()

            result = self.run_in_directory(directory, "add", "--path", str(source), "--rev", "v1")

            self.assertFalse((directory / "odindeps.json").exists())
            self.assertFalse((directory / "src" / "third_party" / "source").exists())
        self.assertEqual(result.returncode, 2)

    def test_identical_add_materializes_a_missing_path_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source = directory / "source"
            source.mkdir()
            directory.joinpath("odindeps.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "dependencies": {"source": {"path": str(source)}},
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_in_directory(directory, "add", "--path", str(source))

            materialized = (directory / "src" / "third_party" / "source").is_dir()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(materialized)

    def test_add_materializes_only_the_selected_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            existing_source = directory / "existing-source"
            existing_source.mkdir()
            added_source = directory / "added-source"
            added_source.mkdir()
            directory.joinpath("odindeps.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "dependencies": {"existing": {"path": str(existing_source)}},
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_in_directory(
                directory,
                "add",
                "--path",
                str(added_source),
                "--name",
                "added",
            )

            existing_destination = directory / "src" / "third_party" / "existing"
            added_destination = directory / "src" / "third_party" / "added"
            self.assertFalse(existing_destination.exists())
            self.assertTrue(added_destination.is_dir())
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_add_reports_invalid_existing_manifest_without_a_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            directory.joinpath("odindeps.json").write_text("{", encoding="utf-8")
            source = directory / "source"
            source.mkdir()

            result = self.run_in_directory(directory, "add", "--path", str(source))

        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.startswith("odindeps:"), result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
