"""Static contracts for the checked-in GitHub automation."""

from __future__ import annotations

import re
import shlex
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATHS = (
    ROOT / ".github/workflows/ci.yml",
    ROOT / ".github/workflows/release.yml",
)

# Each entry was resolved against the corresponding upstream release before
# review. A syntactically valid but unknown SHA must not pass this test.
REVIEWED_ACTION_PINS = {
    "actions/checkout": (
        "3d3c42e5aac5ba805825da76410c181273ba90b1",
        "v7.0.1",
    ),
    "jdx/mise-action": (
        "9e7f7633ff6f6d6048a9418a68d48f288f50eb14",
        "v4.2.3",
    ),
}
EXPECTED_RELEASE_ASSETS = ("odindeps", "odindeps.cmd", "odindeps.sha256")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def run_scripts(workflow: str) -> list[str]:
    """Return single-line and literal-block `run` values without parsing YAML."""
    lines = workflow.splitlines()
    scripts: list[str] = []
    index = 0
    while index < len(lines):
        match = re.match(
            r"^(?P<indent>\s*)(?:-\s+)?run:\s*(?P<value>.*)$",
            lines[index],
        )
        if match is None:
            index += 1
            continue

        value = match.group("value").strip()
        if value not in {"|", "|-", "|+"}:
            scripts.append(value)
            index += 1
            continue

        parent_indent = len(match.group("indent"))
        index += 1
        block: list[str] = []
        while index < len(lines):
            line = lines[index]
            if line and len(line) - len(line.lstrip()) <= parent_indent:
                break
            block.append(line)
            index += 1
        scripts.append("\n".join(block))
    return scripts


def job_body(workflow: str, job_name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(job_name)}:\s*\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:\s*\n|\Z)",
        workflow,
    )
    if match is None:
        raise AssertionError(f"missing {job_name!r} job")
    return match.group("body")


def release_create_assets(script: str) -> tuple[str, ...]:
    logical_script = script.replace("\\\n", " ")
    create_line = next(
        (line.strip() for line in logical_script.splitlines() if "gh release create " in line),
        None,
    )
    if create_line is None:
        raise AssertionError("missing gh release create command")

    tokens = shlex.split(create_line)
    create_index = tokens.index("create")
    operands = tokens[create_index + 1 :]
    if not operands:
        raise AssertionError("gh release create is missing its tag")

    assets: list[str] = []
    for token in operands[1:]:
        if token.startswith("-"):
            break
        assets.append(token)
    return tuple(assets)


class AutomationTests(unittest.TestCase):
    def test_every_external_action_uses_a_reviewed_resolvable_full_sha(self) -> None:
        discovered_actions: set[str] = set()

        for path in WORKFLOW_PATHS:
            workflow = read(path)
            for line_number, line in enumerate(workflow.splitlines(), start=1):
                if "uses:" not in line:
                    continue
                match = re.search(
                    r"\buses:\s*['\"]?(?P<action>[^@\s'\"]+)@"
                    r"(?P<ref>[^#\s'\"]+).*?#\s*(?P<release>\S+)\s*$",
                    line,
                )
                self.assertIsNotNone(
                    match,
                    f"{path.name}:{line_number} must name a pinned action and upstream release",
                )
                assert match is not None
                action = match.group("action")
                ref = match.group("ref")
                release = match.group("release")
                self.assertRegex(ref, r"\A[0-9a-f]{40}\Z")
                self.assertIn(action, REVIEWED_ACTION_PINS)
                self.assertEqual((ref, release), REVIEWED_ACTION_PINS[action])
                discovered_actions.add(action)

        self.assertEqual(discovered_actions, set(REVIEWED_ACTION_PINS))

    def test_ci_is_a_blocking_three_platform_read_only_gate(self) -> None:
        workflow = read(ROOT / ".github/workflows/ci.yml")

        self.assertIn("ubuntu-latest, macos-latest, windows-latest", workflow)
        self.assertIn("permissions: {contents: read}", workflow)
        self.assertIn("cancel-in-progress: true", workflow)
        self.assertNotIn("continue-on-error", workflow)
        self.assertNotIn("pull_request_target", workflow)
        self.assertNotIn("secrets.", workflow)
        self.assertIn("mise run check", workflow)

    def test_mise_unittest_discovery_patterns_are_portable_to_windows(self) -> None:
        config = read(ROOT / "mise.toml")
        discovery_commands = [line for line in config.splitlines() if "python -m unittest discover" in line]

        self.assertEqual(len(discovery_commands), 3)
        for command in discovery_commands:
            with self.subTest(command=command):
                self.assertIn("-p test_*.py", command)
                self.assertNotIn("'test_*.py'", command)

    def test_all_uv_invocations_use_the_locked_project_environment(self) -> None:
        sources = [read(ROOT / "mise.toml"), *(read(path) for path in WORKFLOW_PATHS)]
        invocations = [
            match.group(0) for source in sources for match in re.finditer(r"\buv\s+(?:run|sync)\b[^&;\n]*", source)
        ]

        self.assertTrue(invocations, "expected at least one uv invocation")
        for invocation in invocations:
            with self.subTest(invocation=invocation):
                self.assertIn("--locked", invocation)

    def test_ci_checks_posix_mode_and_shebang_then_executes_the_copy_directly(self) -> None:
        scripts = "\n".join(run_scripts(read(ROOT / ".github/workflows/ci.yml")))

        self.assertIn("test -x odindeps", scripts)
        self.assertIn("#!/usr/bin/env python3", scripts)
        self.assertRegex(scripts, r"(?m)(?:^|&&\s*)/tmp/odindeps --help(?:\s*&&|$)")
        self.assertNotRegex(scripts, r"\bpython3?\s+/tmp/odindeps\b")
        self.assertIn("odindeps.cmd --help", scripts)

    def test_ci_materializes_a_filtered_clone_on_windows_without_the_odin_toolchain(self) -> None:
        workflow = read(ROOT / ".github/workflows/ci.yml")
        check = job_body(workflow, "check")

        self.assertIn("Materialize the filtered clone on Windows", check)
        self.assertIn("examples/odin-collection-import/myproject", check)
        self.assertIn("python ../../../odindeps sync", check)
        self.assertIn("third_party/slog/LICENSE", check)
        self.assertIn("if: runner.os == 'Windows'", check)

    def test_ci_runs_both_odin_examples_end_to_end(self) -> None:
        workflow = read(ROOT / ".github/workflows/ci.yml")
        examples = job_body(workflow, "odin-examples")
        scripts = "\n".join(run_scripts("  odin-examples:\n" + examples))

        self.assertIn("ubuntu-latest, macos-latest", examples)
        self.assertNotIn("windows-latest", examples)
        self.assertNotIn("shell: pwsh", examples)
        self.assertIn("examples/odin-collection-import/myproject", examples)
        self.assertIn("examples/odin-relative-import/myproject", examples)
        for command in (
            "mise run install",
            "mise run sync",
            "mise run verify",
            "python ../../../odindeps sync",
            "odin run src",
        ):
            with self.subTest(command=command):
                self.assertIn(command, scripts)

    def test_manual_release_tag_enters_shell_only_through_environment(self) -> None:
        workflow = read(ROOT / ".github/workflows/release.yml")
        scripts = "\n".join(run_scripts(workflow))

        self.assertNotIn("${{ inputs.", scripts)
        self.assertNotIn("${{ github.event.inputs.", scripts)
        self.assertNotIn("${{ github.ref_name", scripts)
        requested_tag_env = re.search(
            r"(?m)^\s*(?P<name>[A-Z][A-Z0-9_]*):\s*['\"]?"
            r"\$\{\{\s*inputs\.tag\s*\|\|\s*github\.ref_name\s*\}\}",
            workflow,
        )
        self.assertIsNotNone(
            requested_tag_env,
            "workflow_dispatch tag must cross the expression/shell boundary through env",
        )
        assert requested_tag_env is not None
        self.assertIn(f"${requested_tag_env.group('name')}", scripts)

    def test_publish_uses_only_the_sanitized_tag_and_commit_from_verify(self) -> None:
        workflow = read(ROOT / ".github/workflows/release.yml")
        publish = job_body(workflow, "publish")
        publish_scripts = "\n".join(run_scripts("  publish:\n" + publish))

        self.assertIn("needs.verify.outputs.tag", publish)
        self.assertIn("needs.verify.outputs.commit", publish)
        self.assertNotIn("inputs.tag", publish_scripts)
        self.assertNotIn("github.ref_name", publish_scripts)
        self.assertNotIn("steps.tag.outputs", publish_scripts)

        sanitized_tag_env = re.search(
            r"(?m)^\s*(?P<name>[A-Z][A-Z0-9_]*):\s*['\"]?"
            r"\$\{\{\s*needs\.verify\.outputs\.tag\s*\}\}",
            publish,
        )
        self.assertIsNotNone(
            sanitized_tag_env,
            "publish must receive the validated verify output through env",
        )
        assert sanitized_tag_env is not None
        self.assertIn(f"${sanitized_tag_env.group('name')}", publish_scripts)

    def test_release_serializes_publication_without_cancelling_it(self) -> None:
        workflow = read(ROOT / ".github/workflows/release.yml")

        self.assertRegex(
            workflow,
            r"(?ms)^concurrency:\s*\n\s+group:\s*release-[^\n]+\n"
            r"\s+cancel-in-progress:\s*false\s*$",
        )

    def test_release_permissions_are_read_only_except_for_publish(self) -> None:
        ci = read(ROOT / ".github/workflows/ci.yml")
        release = read(ROOT / ".github/workflows/release.yml")
        verify = job_body(release, "verify")
        publish = job_body(release, "publish")
        release_defaults = release[: release.index("jobs:")]

        self.assertIn("permissions: {contents: read}", ci)
        self.assertNotIn("contents: write", ci)
        self.assertIn("permissions: {contents: read}", release_defaults)
        self.assertNotIn("contents: write", verify)
        self.assertEqual(release.count("permissions: {contents: write}"), 1)
        self.assertIn("permissions: {contents: write}", publish)
        self.assertNotIn("secrets.", release)
        self.assertIn("github.token", publish)

    def test_project_version_is_parsed_semantically(self) -> None:
        workflow = read(ROOT / ".github/workflows/release.yml")

        self.assertIn("tomllib", workflow)
        self.assertRegex(
            workflow,
            r"\[['\"]project['\"]\]\[['\"]version['\"]\]",
        )
        self.assertNotRegex(
            workflow,
            r"(?im)^\s*grep\b[^\n]*\bpyproject\.toml\b",
        )

    def test_release_uses_changelog_notes_with_checksum_and_installation_text(self) -> None:
        workflow = read(ROOT / ".github/workflows/release.yml")
        publish_script = "\n".join(run_scripts("  publish:\n" + job_body(workflow, "publish")))

        self.assertIn("CHANGELOG.md", publish_script)
        self.assertIn("--notes-file", publish_script)
        self.assertNotIn("--generate-notes", publish_script)
        self.assertNotIn("cat CHANGELOG.md", publish_script)
        self.assertIn("release_heading", publish_script)
        self.assertRegex(publish_script, r"(?i)SHA-?256")
        self.assertRegex(publish_script, r"(?i)install")
        self.assertIn("odindeps.sha256", publish_script)

    def test_release_create_verifies_existing_tag_and_names_the_exact_assets(self) -> None:
        publish_script = "\n".join(
            run_scripts("  publish:\n" + job_body(read(ROOT / ".github/workflows/release.yml"), "publish"))
        )

        self.assertIn("--verify-tag", publish_script)
        self.assertEqual(release_create_assets(publish_script), EXPECTED_RELEASE_ASSETS)

    def test_release_asset_contract_rejects_an_extra_asset(self) -> None:
        fixture = 'gh release create "$RELEASE_TAG" odindeps odindeps.cmd odindeps.sha256 unexpected.zip --verify-tag'

        self.assertNotEqual(release_create_assets(fixture), EXPECTED_RELEASE_ASSETS)

    def test_release_enumerates_and_verifies_uploaded_assets(self) -> None:
        publish_script = "\n".join(
            run_scripts("  publish:\n" + job_body(read(ROOT / ".github/workflows/release.yml"), "publish"))
        )
        create_position = publish_script.index("gh release create ")
        post_create = publish_script[create_position:]

        self.assertIn("--json assets", post_create)
        self.assertIn(".assets[].name", post_create)
        self.assertIn("printf '%s\\n' odindeps odindeps.cmd odindeps.sha256", post_create)
        self.assertIn('test "$actual_assets" = "$expected_assets"', post_create)
        self.assertIn("gh release download", post_create)
        self.assertIn("--pattern odindeps", post_create)
        self.assertIn("--pattern odindeps.cmd", post_create)
        self.assertIn("--pattern odindeps.sha256", post_create)
        self.assertRegex(post_create, r"sha256sum\s+--check\b")
        self.assertRegex(post_create, r"\bcmp\s+odindeps\s+\S+/odindeps\b")
        self.assertRegex(post_create, r"\bcmp\s+odindeps\.cmd\s+\S+/odindeps\.cmd\b")

    def test_release_recovers_a_draft_and_publishes_only_after_asset_verification(self) -> None:
        publish_script = "\n".join(
            run_scripts("  publish:\n" + job_body(read(ROOT / ".github/workflows/release.yml"), "publish"))
        )

        self.assertIn("--draft", publish_script)
        self.assertIn("gh release upload", publish_script)
        self.assertIn("--clobber", publish_script)
        self.assertIn('gh release edit "$RELEASE_TAG" --draft=false', publish_script)
        self.assertLess(publish_script.index("sha256sum --check"), publish_script.index("--draft=false"))

    def test_release_rechecks_the_copied_posix_executable_directly(self) -> None:
        scripts = "\n".join(run_scripts(read(ROOT / ".github/workflows/release.yml")))

        self.assertRegex(scripts, r"(?m)(?:^|&&\s*)/tmp/odindeps --help(?:\s*&&|$)")
        self.assertNotRegex(scripts, r"\bpython3?\s+/tmp/odindeps\b")

    def test_release_fetches_tags_in_publish_and_uses_python_on_windows(self) -> None:
        release = read(ROOT / ".github/workflows/release.yml")
        publish = job_body(release, "publish")

        self.assertIn("fetch-depth: 0", publish)
        self.assertIn("python ./odindeps --version", release)
        self.assertIn("odindeps.cmd --version", release)
        self.assertNotIn("& ./odindeps --version", release)

    def test_contributing_documents_the_reviewed_version_contract(self) -> None:
        contributing = read(ROOT / "CONTRIBUTING.md")

        for source in ("odindeps --version", "pyproject.toml", "CHANGELOG.md", "vX.Y.Z"):
            with self.subTest(source=source):
                self.assertIn(source, contributing)
        self.assertRegex(contributing, r"(?i)(all four|four version sources).*\bagree\b")
        self.assertRegex(contributing, r"(?i)human[- ]created.*tag")


if __name__ == "__main__":
    unittest.main()
