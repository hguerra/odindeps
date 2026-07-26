"""End-to-end tests for the local-copy synchronization strategy."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "odindeps"


class LocalCopyTests(unittest.TestCase):
    def run_sync(self, project: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "sync", *arguments],
            check=False,
            capture_output=True,
            cwd=project,
            text=True,
        )

    def write_manifest(
        self,
        project: Path,
        source: Path,
        *,
        destination_root: str | None = None,
    ) -> Path:
        manifest: dict[str, object] = {
            "schema_version": 1,
            "dependencies": {"sample": {"path": str(source)}},
        }
        if destination_root is not None:
            manifest["defaults"] = {"destination_root": destination_root}
        project.joinpath("odindeps.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        return project / (destination_root or "third_party") / "sample"

    def test_sync_copies_a_local_directory_with_metadata_and_force_refreshes_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            source.mkdir()
            source.joinpath("message.txt").write_text("first", encoding="utf-8")
            project = root / "project"
            project.mkdir()
            destination = self.write_manifest(project, source)

            first = self.run_sync(project)
            metadata = json.loads(destination.joinpath(".odindeps-meta.json").read_text(encoding="utf-8"))
            source.joinpath("message.txt").write_text("second", encoding="utf-8")
            normal = self.run_sync(project)
            forced = self.run_sync(project, "--force")
            copied_text = destination.joinpath("message.txt").read_text(encoding="utf-8")

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(metadata["name"], "sample")
        self.assertEqual(metadata["dependency_kind"], "path")
        self.assertEqual(normal.returncode, 0, normal.stderr)
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertEqual(copied_text, "second")

    def test_sync_refuses_an_unowned_destination_even_with_force(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            source.mkdir()
            project = root / "project"
            project.mkdir()
            destination = self.write_manifest(project, source)
            destination.mkdir(parents=True)
            destination.joinpath("user.txt").write_text("keep", encoding="utf-8")

            result = self.run_sync(project, "--force")
            retained = destination.joinpath("user.txt").read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 3)
        self.assertTrue(result.stderr.startswith("odindeps:"), result.stderr)
        self.assertEqual(retained, "keep")

    def test_sync_rejects_a_destination_nested_inside_its_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            project.mkdir()
            source = project / "src"
            source.mkdir()
            self.write_manifest(project, source, destination_root="src/third_party")

            result = self.run_sync(project)

        self.assertEqual(result.returncode, 3)
        self.assertTrue(result.stderr.startswith("odindeps:"), result.stderr)

    def test_sync_preflights_all_local_sources_before_copying_any_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            source.mkdir()
            project = root / "project"
            project.mkdir()
            project.joinpath("odindeps.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "dependencies": {"first": {"path": str(source)}, "second": {"path": "missing"}},
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_sync(project)

            self.assertFalse((project / "third_party" / "first").exists())
        self.assertEqual(result.returncode, 5)

    @unittest.skipIf(sys.platform.startswith("win"), "symlink-parent behavior is POSIX-specific")
    def test_sync_refuses_a_destination_that_escapes_through_a_parent_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            source.mkdir()
            outside = root / "outside"
            outside.mkdir()
            project = root / "project"
            project.mkdir()
            project.joinpath("third_party").symlink_to(outside, target_is_directory=True)
            self.write_manifest(project, source)

            result = self.run_sync(project)

            self.assertFalse((outside / "sample").exists())
        self.assertEqual(result.returncode, 3)

    @unittest.skipIf(sys.platform.startswith("win"), "native Windows does not support local symlinks")
    def test_sync_creates_a_relative_local_symlink_without_modifying_its_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            source.mkdir()
            source.joinpath("value.txt").write_text("original", encoding="utf-8")
            project = root / "project"
            project.mkdir()
            project.joinpath("odindeps.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "dependencies": {
                            "sample": {"path": str(source), "options": {"local": {"strategy": "symlink"}}}
                        },
                    }
                ),
                encoding="utf-8",
            )
            destination = project / "third_party" / "sample"

            result = self.run_sync(project)

            link_target = destination.readlink()
            is_link = destination.is_symlink()
            source_text = source.joinpath("value.txt").read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(is_link)
        self.assertFalse(link_target.is_absolute())
        self.assertEqual(source_text, "original")

    def test_sync_honors_an_explicit_src_third_party_override(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            source.mkdir()
            source.joinpath("value.txt").write_text("original", encoding="utf-8")
            project = root / "project"
            project.mkdir()
            destination = self.write_manifest(
                project,
                source,
                destination_root="src/third_party",
            )

            result = self.run_sync(project)

            self.assertTrue(destination.joinpath("value.txt").is_file())
            self.assertFalse((project / "third_party" / "sample").exists())
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
