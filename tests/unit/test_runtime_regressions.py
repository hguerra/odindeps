"""Regression tests for validation and command-line error contracts."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.unit.support import load_odindeps


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "odindeps"
odindeps = load_odindeps()


class RuntimeValidationRegressionTests(unittest.TestCase):
    def test_clone_file_patterns_must_be_project_relative_posix_globs(self) -> None:
        invalid_patterns = (
            "../*.odin",
            "/absolute/*.odin",
            r"src\*.odin",
            "C:/outside/*.odin",
        )

        for pattern in invalid_patterns:
            manifest = {
                "schema_version": 1,
                "dependencies": {
                    "library": {
                        "git": "example.test/team/library",
                        "rev": "v1",
                        "options": {"git": {"clone": {"includes": [pattern]}}},
                    }
                },
            }
            with self.subTest(pattern=pattern), self.assertRaises(odindeps.ValidationError):
                odindeps.parse_manifest(manifest)

    def test_legacy_clone_files_field_is_rejected(self) -> None:
        with self.assertRaises(odindeps.ValidationError):
            odindeps.parse_manifest(
                {
                    "schema_version": 1,
                    "dependencies": {
                        "library": {
                            "git": "example.test/team/library",
                            "rev": "v1",
                            "options": {"git": {"clone": {"files": ["*.odin"]}}},
                        }
                    },
                }
            )

    def test_windows_drive_destination_is_not_a_project_relative_path(self) -> None:
        manifest = {
            "schema_version": 1,
            "dependencies": {"library": {"path": "../library"}},
            "defaults": {"destination_root": "C:/outside"},
        }

        with self.assertRaises(odindeps.ValidationError):
            odindeps.parse_manifest(manifest, platform="windows")

    def test_invalid_utf8_manifest_is_a_validation_error_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            project.joinpath("odindeps.json").write_bytes(b"\xff")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "sync"],
                cwd=project,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.startswith("odindeps:"), result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_argparse_errors_use_the_application_diagnostic_prefix(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "sync", "--unknown-option"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.startswith("odindeps:"), result.stderr)

    def test_glob_matching_with_many_recursive_segments_is_linear_in_its_state_space(self) -> None:
        path = "/".join(["source"] * 24)
        pattern = "/".join(["**"] * 24 + ["missing.odin"])

        self.assertFalse(odindeps._path_matches_pattern(path, pattern))


if __name__ == "__main__":
    unittest.main()
