"""Tests for pure Git planning helpers."""

from __future__ import annotations

import unittest

from tests.unit.support import load_odindeps

odindeps = load_odindeps()


class GitPlanningTests(unittest.TestCase):
    def test_derives_https_and_ssh_remotes_from_a_neutral_source(self) -> None:
        self.assertEqual(
            odindeps.derive_remote("github.com/hguerra/odin-slog", "https"),
            "https://github.com/hguerra/odin-slog.git",
        )
        self.assertEqual(
            odindeps.derive_remote("github.com/hguerra/odin-slog.git", "ssh"),
            "git@github.com:hguerra/odin-slog.git",
        )

    def test_rejects_invalid_transport(self) -> None:
        with self.assertRaises(odindeps.ValidationError):
            odindeps.derive_remote("github.com/hguerra/odin-slog", "file")

    def test_git_error_redacts_credentials_from_subprocess_output(self) -> None:
        message = odindeps.sanitize_git_error("fatal: https://alice:secret@example.test/repo denied")

        self.assertNotIn("alice", message)
        self.assertNotIn("secret", message)
        self.assertEqual(message, "Git command failed")

    def test_cache_key_changes_when_the_commit_or_filters_change(self) -> None:
        base = odindeps.cache_key("example.test/team/library", "a" * 40, (), ())

        self.assertEqual(base, odindeps.cache_key("example.test/team/library", "a" * 40, (), ()))
        self.assertNotEqual(base, odindeps.cache_key("example.test/team/library", "b" * 40, (), ()))
        self.assertNotEqual(base, odindeps.cache_key("example.test/team/library", "a" * 40, ("*.odin",), ()))
        self.assertNotEqual(base, odindeps.cache_key("example.test/team/library", "a" * 40, (), ("tests/**",)))


if __name__ == "__main__":
    unittest.main()
