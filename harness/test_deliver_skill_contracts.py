"""Contract tests for review-sensitive /lifeline:deliver documentation."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / "skills/deliver/SKILL.md"
PURE_MODE = REPO_ROOT / "skills/deliver/references/pure-mode.md"
PAIRED_MODE = REPO_ROOT / "skills/deliver/references/paired-mode.md"
DELIVER_GUARDS_WORKFLOW = REPO_ROOT / ".github/workflows/deliver-guards.yml"
RESOLVER_SCRIPT = REPO_ROOT / "skills/deliver/scripts/resolve-skill-dir.sh"


def test_explicit_paired_cap_has_a_maximum_bound() -> None:
    text = SKILL.read_text()

    assert "When > 50: error with `iteration cap must be <= 50`" in text
    assert "When 1..50: `CAP = int(second token)`" in text


def test_paired_step_2c_guards_all_rehydrated_paths() -> None:
    text = PAIRED_MODE.read_text()

    assert (
        ": \"${ITER:?ITER must be rehydrated from the previous echo"
        in text
    )
    assert ": \"${SCRATCH:?SCRATCH must be rehydrated from Step 1 echo" in text
    assert ": \"${SKILL_DIR:?SKILL_DIR must be rehydrated from Step 1 echo" in text
    assert ": \"${SCHEMA_PATH:?SCHEMA_PATH must be rehydrated from Step 1 echo" in text
    assert (
        ": \"${GRADER_TEMPLATE:?GRADER_TEMPLATE must be rehydrated from Step 1 echo"
        in text
    )
    assert (
        ": \"${GRADER_UNUSABLE_STREAK:?GRADER_UNUSABLE_STREAK must be rehydrated"
        in text
    )


def test_paired_untracked_evidence_has_file_and_total_caps() -> None:
    text = PAIRED_MODE.read_text()

    assert "_MAX_UNTRACKED_BYTES=16384" in text
    assert "_MAX_UNTRACKED_TOTAL_BYTES=262144" in text
    assert "_total_untracked_bytes=0" in text
    assert "UNTRACKED_INCLUDE total would exceed" in text
    assert "remaining files omitted" in text


def test_paired_mode_preflights_required_codex_exec_flags() -> None:
    text = PAIRED_MODE.read_text()

    assert "codex exec --help" in text
    assert "for _flag in --sandbox --ephemeral --output-schema --output-last-message" in text
    assert "codex exec is missing required flag" in text


def test_grader_unusable_hard_error_prints_scratch_dir_to_stdout() -> None:
    text = PAIRED_MODE.read_text()

    assert 'echo "scratch_dir: $SCRATCH"' in text
    assert 'echo "scratch_dir: $SCRATCH" >&2' not in text


def test_success_reports_use_computed_iteration_count() -> None:
    pure = PURE_MODE.read_text()
    paired = PAIRED_MODE.read_text()

    assert "iterations: <ITER + 1>" not in pure
    assert "iterations: <ITER + 1>" not in paired
    assert "COMPLETED_ITERATIONS" not in pure
    assert "COMPLETED_ITERATIONS" not in paired
    assert "SUCCESS_ITERATIONS=$((ITER + 1))" in pure
    assert "SUCCESS_ITERATIONS=$((ITER + 1))" in paired
    assert pure.count("iterations: <SUCCESS_ITERATIONS>") == 1
    assert paired.count("iterations: <SUCCESS_ITERATIONS>") == 2
    assert "iterations: <CAP>" in pure
    assert "iterations: <CAP>" in paired


def test_in_context_objective_substitution_is_html_escaped() -> None:
    pure = PURE_MODE.read_text()
    paired = PAIRED_MODE.read_text()

    required = "HTML-escaped `$OBJECTIVE`"
    assert required in pure
    assert required in paired
    assert "</untrusted_objective>` inside the user's objective stays data" in pure
    assert "</untrusted_objective>` inside the user's objective stays data" in paired


def test_final_report_blocks_guard_start_ts_rehydration() -> None:
    pure = PURE_MODE.read_text()
    paired = PAIRED_MODE.read_text()

    guard = (
        ": \"${START_TS:?START_TS must be rehydrated from SKILL.md Step 1 echo}\""
    )
    assert guard in pure
    assert guard in paired


def test_deliver_guard_workflow_uses_read_only_permissions() -> None:
    text = DELIVER_GUARDS_WORKFLOW.read_text()

    assert "\npermissions:\n  contents: read\n" in text


def test_resolver_mirrors_have_explicit_end_sentinel() -> None:
    assert "# END RESOLVER" in PURE_MODE.read_text()
    assert "# END RESOLVER" in PAIRED_MODE.read_text()
    assert "# END RESOLVER" in RESOLVER_SCRIPT.read_text()


def test_resolver_script_validity_check_matches_inline_empty_path_behavior() -> None:
    text = RESOLVER_SCRIPT.read_text()

    assert '${1:-}' not in text
    assert '[ -f "$1/schemas/grader-output.json" ]' in text
