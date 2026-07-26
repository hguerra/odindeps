"""Tests for strict, immutable odindeps manifest validation."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tests.unit.support import load_odindeps


odindeps = load_odindeps()


class ManifestTests(unittest.TestCase):
    def test_new_manifest_vocabulary_distinguishes_git_and_path_dependencies(self) -> None:
        manifest = odindeps.parse_manifest(
            {
                "schema_version": 1,
                "dependencies": {
                    "parser": {"git": "github.com/example/parser", "rev": "v1"},
                    "shared": {"path": "../shared"},
                },
                "defaults": {"destination_root": "vendor"},
            }
        )

        self.assertEqual(manifest.dependencies["parser"].git, "github.com/example/parser")
        self.assertEqual(manifest.dependencies["shared"].path, "../shared")
        self.assertEqual(manifest.defaults["destination_root"], "vendor")

    def test_legacy_manifest_vocabulary_is_rejected(self) -> None:
        legacy_manifests = (
            {"schema_version": 1, "deps": {}},
            {"schema_version": 1, "dependencies": {"dep": {"source": "github.com/a/b", "rev": "v1"}}},
            {"schema_version": 1, "dependencies": {"dep": {"local": "../dep"}}},
            {"schema_version": 1, "dependencies": {}, "options": {}},
        )

        for value in legacy_manifests:
            with self.subTest(value=value), self.assertRaises(odindeps.ValidationError):
                odindeps.parse_manifest(value)

    def test_checked_in_json_schema_describes_the_public_vocabulary(self) -> None:
        schema_path = Path(__file__).resolve().parents[2] / "odindeps.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertIn("dependencies", schema["properties"])
        self.assertIn("defaults", schema["properties"])
        self.assertFalse(schema["additionalProperties"])

    def test_checked_in_json_schema_rejects_values_rejected_by_the_runtime_parser(self) -> None:
        schema_path = Path(__file__).resolve().parents[2] / "odindeps.schema.json"
        definitions = json.loads(schema_path.read_text(encoding="utf-8"))["$defs"]
        git_pattern = definitions["git_dependency"]["properties"]["git"]["pattern"]
        revision_pattern = definitions["git_dependency"]["properties"]["rev"]["pattern"]
        destination_pattern = definitions["portable_path"]["pattern"]
        clone_properties = definitions["git_options"]["properties"]["clone"]["properties"]
        glob_pattern = definitions["portable_glob"]["pattern"]

        self.assertIsNone(re.fullmatch(git_pattern, "https://github.com/a/b"))
        self.assertIsNone(re.fullmatch(revision_pattern, "-bad"))
        self.assertIsNone(re.fullmatch(destination_pattern, "../outside"))
        self.assertIsNone(re.fullmatch(destination_pattern, "vendor\\outside"))
        self.assertIsNone(re.fullmatch(destination_pattern, "C:/outside"))
        self.assertIsNotNone(re.fullmatch(git_pattern, "github.com/a/b"))
        self.assertIsNotNone(re.fullmatch(revision_pattern, "v1"))
        self.assertIsNotNone(re.fullmatch(destination_pattern, "src/third_party"))
        for name in ("includes", "excludes"):
            self.assertEqual(
                clone_properties[name]["items"]["$ref"],
                "#/$defs/portable_glob",
            )
            for invalid in ("../*.odin", "/absolute/*.odin", r"src\*.odin", "C:/outside/*.odin"):
                with self.subTest(name=name, invalid=invalid):
                    self.assertIsNone(re.fullmatch(glob_pattern, invalid))
            self.assertIsNotNone(re.fullmatch(glob_pattern, "**/*.odin"))

    def test_minimal_manifest_normalizes_to_immutable_records(self) -> None:
        manifest = odindeps.parse_manifest({"schema_version": 1, "dependencies": {}})

        self.assertEqual(manifest.schema_version, 1)
        self.assertEqual(dict(manifest.dependencies), {})
        with self.assertRaises(TypeError):
            manifest.dependencies["other"] = object()

    def test_json_parser_rejects_syntax_errors_and_duplicate_keys(self) -> None:
        for document in (
            '{"schema_version": 1, "dependencies": {},}',
            '{"schema_version": 1, "schema_version": 1, "dependencies": {}}',
        ):
            with self.subTest(document=document), self.assertRaises(odindeps.ValidationError):
                odindeps.parse_manifest_json(document)

    def test_complete_manifest_accepts_git_and_local_variants(self) -> None:
        manifest = odindeps.parse_manifest(
            {
                "schema_version": 1,
                "dependencies": {
                    "slog": {"git": "github.com/hguerra/odin-slog", "rev": "v0.0.1"},
                    "shared": {"path": "../shared/config"},
                },
                "defaults": {"destination_root": "vendor", "transport": "ssh"},
            }
        )

        self.assertEqual(manifest.dependencies["slog"].git, "github.com/hguerra/odin-slog")
        self.assertEqual(manifest.dependencies["shared"].path, "../shared/config")
        self.assertEqual(manifest.defaults["destination_root"], "vendor")

    def test_unknown_or_ambiguous_fields_are_validation_errors(self) -> None:
        cases = (
            {"schema_version": 1, "dependencies": {}, "unexpected": True},
            {"schema_version": 1, "dependencies": {"dep": {"git": "github.com/a/b", "rev": "v1", "path": "x"}}},
            {"schema_version": 1, "dependencies": {"dep": {"git": "github.com/a/b"}}},
        )

        for value in cases:
            with self.subTest(value=value), self.assertRaises(odindeps.ValidationError) as raised:
                odindeps.parse_manifest(value)
            self.assertEqual(raised.exception.exit_code, 2)

    def test_rejects_invalid_names_sources_revisions_and_destination_paths(self) -> None:
        cases = (
            {"schema_version": 1, "dependencies": {"bad/name": {"path": "local"}}},
            {"schema_version": 1, "dependencies": {"dep": {"git": "https://github.com/a/b", "rev": "v1"}}},
            {"schema_version": 1, "dependencies": {"dep": {"git": "github.com/a/b", "rev": "-bad"}}},
            {"schema_version": 1, "dependencies": {}, "defaults": {"destination_root": "../outside"}},
        )

        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(odindeps.ValidationError):
                    odindeps.parse_manifest(value)

    def test_rejects_duplicate_normalized_destinations(self) -> None:
        with self.assertRaisesRegex(odindeps.ValidationError, "destination"):
            odindeps.parse_manifest(
                {
                    "schema_version": 1,
                    "dependencies": {
                        "one": {"path": "one"},
                        "ONE": {"path": "two"},
                    },
                    "defaults": {"destination_root": "vendor"},
                },
                platform="windows",
            )

    def test_rejects_inapplicable_and_windows_unsupported_options(self) -> None:
        with self.assertRaises(odindeps.ValidationError):
            odindeps.parse_manifest(
                {"schema_version": 1, "dependencies": {"local": {"path": "source", "options": {"git": {}}}}}
            )

        with self.assertRaises(odindeps.ValidationError):
            odindeps.parse_manifest(
                {
                    "schema_version": 1,
                    "dependencies": {"local": {"path": "source", "options": {"local": {"strategy": "symlink"}}}},
                },
                platform="windows",
            )

    def test_windows_path_dependency_ignores_git_cache_symlink_default(self) -> None:
        manifest = odindeps.parse_manifest(
            {
                "schema_version": 1,
                "dependencies": {"shared": {"path": "../shared"}},
                "defaults": {"cache": {"mode": "symlink"}},
            },
            platform="windows",
        )

        self.assertEqual(manifest.dependencies["shared"].path, "../shared")


if __name__ == "__main__":
    unittest.main()
