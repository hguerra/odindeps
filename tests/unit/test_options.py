"""Tests for deterministic recursive option merging."""

from __future__ import annotations

import unittest

from tests.unit.support import load_odindeps


odindeps = load_odindeps()


class OptionTests(unittest.TestCase):
    def test_dependency_options_override_global_options_recursively_and_replace_lists(self) -> None:
        manifest = odindeps.parse_manifest(
            {
                "schema_version": 1,
                "dependencies": {
                    "parser": {
                        "git": "github.com/example/parser",
                        "rev": "v1",
                        "options": {"git": {"clone": {"files": ["src/**/*.odin"]}}},
                    }
                },
                "defaults": {
                    "destination_root": "vendor",
                    "git": {"clone": {"files": ["*.odin", "LICENSE"]}},
                },
            }
        )

        options = odindeps.effective_options(manifest, manifest.dependencies["parser"])

        self.assertEqual(options["destination_root"], "vendor")
        self.assertEqual(options["transport"], "https")
        self.assertEqual(options["git"]["clone"]["files"], ("src/**/*.odin",))
        self.assertTrue(options["git"]["subtree"]["squash"])


if __name__ == "__main__":
    unittest.main()
