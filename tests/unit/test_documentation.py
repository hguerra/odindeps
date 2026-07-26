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

        self.assertIn("<summary><strong>Install odindeps</strong></summary>", readme)
        self.assertIn("<summary><strong>Remove odindeps</strong></summary>", readme)
        self.assertIn("$HOME/.local/bin", readme)
        self.assertIn("releases/latest/download/odindeps", readme)
        self.assertIn("odindeps.sha256", readme)
        self.assertIn("Get-FileHash", readme)

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


if __name__ == "__main__":
    unittest.main()
