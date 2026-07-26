"""Tests for deterministic recursive option merging."""

from __future__ import annotations

import unittest

from tests.unit.support import load_odindeps

odindeps = load_odindeps()


class OptionTests(unittest.TestCase):
    def test_minimal_manifest_uses_third_party_builtin_destination_root(self) -> None:
        manifest = odindeps.parse_manifest(
            {
                "schema_version": 1,
                "dependencies": {
                    "parser": {
                        "git": "github.com/example/parser",
                        "rev": "v1",
                    }
                },
            }
        )

        options = odindeps.effective_options(manifest, manifest.dependencies["parser"])

        self.assertEqual(options["destination_root"], "third_party")

    def test_dependency_options_override_global_options_recursively_and_replace_lists(self) -> None:
        manifest = odindeps.parse_manifest(
            {
                "schema_version": 1,
                "dependencies": {
                    "parser": {
                        "git": "github.com/example/parser",
                        "rev": "v1",
                        "options": {"git": {"clone": {"includes": ["src/**/*.odin"]}}},
                    }
                },
                "defaults": {
                    "destination_root": "vendor",
                    "git": {"clone": {"includes": ["*.odin", "LICENSE"], "excludes": ["tests/**"]}},
                },
            }
        )

        options = odindeps.effective_options(manifest, manifest.dependencies["parser"])

        self.assertEqual(options["destination_root"], "vendor")
        self.assertEqual(options["transport"], "https")
        self.assertEqual(options["git"]["clone"]["includes"], ("src/**/*.odin",))
        self.assertEqual(options["git"]["clone"]["excludes"], ("tests/**",))
        self.assertTrue(options["git"]["subtree"]["squash"])

    def test_manifest_can_explicitly_restore_the_old_destination_layout(self) -> None:
        manifest = odindeps.parse_manifest(
            {
                "schema_version": 1,
                "dependencies": {"shared": {"path": "../shared"}},
                "defaults": {"destination_root": "src/third_party"},
            }
        )

        options = odindeps.effective_options(manifest, manifest.dependencies["shared"])

        self.assertEqual(options["destination_root"], "src/third_party")


if __name__ == "__main__":
    unittest.main()
