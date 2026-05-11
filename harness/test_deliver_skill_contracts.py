"""Contract tests for review-sensitive /lifeline:deliver documentation."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / "skills/deliver/SKILL.md"
PURE_MODE = REPO_ROOT / "skills/deliver/references/pure-mode.md"
PAIRED_MODE = REPO_ROOT / "skills/deliver/references/paired-mode.md"


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


def test_success_reports_use_computed_iteration_count() -> None:
    pure = PURE_MODE.read_text()
    paired = PAIRED_MODE.read_text()

    assert "iterations: <ITER + 1>" not in pure
    assert "iterations: <ITER + 1>" not in paired
    assert "COMPLETED_ITERATIONS=$((ITER + 1))" in pure
    assert "COMPLETED_ITERATIONS=$((ITER + 1))" in paired
    assert pure.count("iterations: <COMPLETED_ITERATIONS>") == 1
    assert paired.count("iterations: <COMPLETED_ITERATIONS>") == 2


def test_final_report_blocks_guard_start_ts_rehydration() -> None:
    pure = PURE_MODE.read_text()
    paired = PAIRED_MODE.read_text()

    guard = (
        ": \"${START_TS:?START_TS must be rehydrated from SKILL.md Step 1 echo}\""
    )
    assert guard in pure
    assert guard in paired
