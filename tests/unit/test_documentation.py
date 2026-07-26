"""Contract tests for documented manifest examples."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tests.unit.support import load_odindeps

ROOT = Path(__file__).resolve().parents[2]
JSON_FENCE = re.compile(r"```json\n(.*?)\n```", re.DOTALL)
odindeps = load_odindeps()


class DocumentationTests(unittest.TestCase):
    def test_documentation_uses_the_canonical_git_dependency_example(self) -> None:
        documents = [ROOT / "README.md", *sorted((ROOT / "examples").glob("*/README.md"))]
        documentation = "\n".join(document.read_text(encoding="utf-8") for document in documents)

        self.assertIn("github.com/hguerra/odin-slog", documentation)

    def test_readme_documents_installation_and_removal(self) -> None:
        readme = ROOT.joinpath("README.md").read_text(encoding="utf-8")

        self.assertIn("## Install", readme)
        self.assertIn("<summary><strong>Remove odindeps</strong></summary>", readme)
        self.assertIn("$HOME/.local/bin", readme)
        self.assertIn('version="v0.1.0"', readme)
        self.assertIn("releases/download/$version", readme)
        self.assertIn("releases/latest/download/odindeps", readme)
        self.assertIn("odindeps.sha256", readme)
        self.assertIn("odindeps.cmd", readme)
        self.assertIn("Get-FileHash", readme)
        self.assertIn('mv "$staged_executable" "$install_directory/odindeps"', readme)

    def test_every_documented_json_manifest_uses_the_current_vocabulary(self) -> None:
        documents = [ROOT / "README.md", *sorted((ROOT / "examples").glob("*/README.md"))]
        examples = [
            json.loads(block)
            for document in documents
            for block in JSON_FENCE.findall(document.read_text(encoding="utf-8"))
        ]

        self.assertGreaterEqual(len(examples), 6)
        for example in examples:
            self.assertEqual(example["schema_version"], 1)
            self.assertIn("dependencies", example)
            self.assertNotIn("deps", example)
            odindeps.parse_manifest(example)

    def test_readme_links_both_odin_import_examples(self) -> None:
        readme = ROOT.joinpath("README.md").read_text(encoding="utf-8")

        for example in ("odin-collection-import", "odin-relative-import"):
            with self.subTest(example=example):
                self.assertIn(f"examples/{example}/README.md", readme)
                self.assertTrue(ROOT.joinpath("examples", example, "README.md").is_file())

    def test_checked_in_odin_project_manifests_are_valid(self) -> None:
        projects = (
            ROOT / "examples/odin-collection-import/myproject",
            ROOT / "examples/odin-relative-import/myproject",
        )

        for project in projects:
            with self.subTest(example=project.parent.name):
                manifest = json.loads(project.joinpath("odindeps.json").read_text(encoding="utf-8"))
                odindeps.parse_manifest(manifest)
                self.assertTrue(project.joinpath(".gitignore").is_file())

    def test_odin_examples_demonstrate_collection_and_relative_imports(self) -> None:
        collection_project = ROOT / "examples/odin-collection-import/myproject"
        collection_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(collection_project.glob("**/*"))
            if path.is_file() and "third_party" not in path.parts and ".bin" not in path.parts
        )
        relative_project = ROOT / "examples/odin-relative-import/myproject"
        relative_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(relative_project.glob("**/*"))
            if path.is_file() and "third_party" not in path.parts
        )

        self.assertIn('import "third_party:slog"', collection_sources)
        self.assertIn("-collection:third_party=third_party", collection_sources)
        self.assertIn('import "./third_party/slog"', relative_sources)
        self.assertNotIn("-collection", relative_sources)


if __name__ == "__main__":
    unittest.main()
