"""Contract tests for review-sensitive /lifeline:deliver documentation."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / "skills/deliver/SKILL.md"
PURE_MODE = REPO_ROOT / "skills/deliver/references/pure-mode.md"
PAIRED_MODE = REPO_ROOT / "skills/deliver/references/paired-mode.md"
DELIVER_GUARDS_WORKFLOW = REPO_ROOT / ".github/workflows/deliver-guards.yml"
RESOLVER_SCRIPT = REPO_ROOT / "skills/deliver/scripts/resolve-skill-dir.sh"
NOTICE = REPO_ROOT / "NOTICE"
APACHE_LICENSE = REPO_ROOT / "LICENSE-apache-2.0"


def test_explicit_paired_cap_has_a_maximum_bound() -> None:
    text = SKILL.read_text()

    assert "When ≤ 0: error with `iteration cap must be a positive integer`" in text
    assert "When > 50: error with `iteration cap must be <= 50`" in text
    assert "When 1..50: `CAP = int(second token)`" in text


def test_pair_prefix_parse_has_confirmation_and_escape_hatch() -> None:
    text = SKILL.read_text()

    assert "first whitespace-separated token is `--`" in text
    assert "escape hatch for pure-mode objectives" in text
    assert "Mode parse: paired; objective: <OBJECTIVE>" in text
    assert "/lifeline:deliver -- pair ..." in text


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

    assert '[ -z "${UNTRACKED_INCLUDE+x}" ] && UNTRACKED_INCLUDE=()' in text
    assert "[[ -v UNTRACKED_INCLUDE ]]" not in text
    assert "UNTRACKED_INCLUDE=(${UNTRACKED_INCLUDE" not in text
    assert "_MAX_UNTRACKED_BYTES=16384" in text
    assert "_MAX_UNTRACKED_TOTAL_BYTES=262144" in text
    assert "_total_untracked_bytes=0" in text
    assert "UNTRACKED_INCLUDE total would exceed" in text
    assert "remaining files omitted" in text
    assert "_sz=$(printf '%s' \"$_sz\" | tr -d '[:space:]')" in text


def test_paired_git_diff_head_has_size_cap() -> None:
    text = PAIRED_MODE.read_text()

    assert "git diff HEAD --no-color" in text
    assert "_MAX_GIT_DIFF_HEAD_BYTES=524288" in text
    assert "wc -c" in text
    assert "tr -d '[:space:]'" in text
    assert "head -c \"$_MAX_GIT_DIFF_HEAD_BYTES\" > \"$_truncated_diff_file\"" in text
    assert 'tail -c 1 "$_truncated_diff_file" | od -An -t x1' in text
    assert 'if [ "$_last_truncated_byte" != "0a" ]; then' in text
    assert "sed '$d' \"$_truncated_diff_file\"" in text
    assert "--- diff truncated at ${_MAX_GIT_DIFF_HEAD_BYTES}B on a line boundary ---" in text
    assert "final combined GIT_DIFF_HEAD cap below bounds" in text
    assert text.index("_git_diff_head_bytes=$(printf '%s' \"$GIT_DIFF_HEAD\"") > text.index(
        "GIT_DIFF_HEAD+=$(git diff --no-index --no-color -- /dev/null \"$_f\""
    )


def test_paired_mode_preflights_required_codex_exec_flags() -> None:
    text = PAIRED_MODE.read_text()

    assert '[ -f "$SCHEMA_PATH" ] || { echo "ERROR: grader schema not found' in text
    assert "codex exec --help" in text
    assert "for _flag in --sandbox --ephemeral --output-schema --output-last-message" in text
    assert "codex exec is missing required flag" in text


def test_paired_mode_materializes_objective_without_shell_state() -> None:
    text = PAIRED_MODE.read_text()

    assert "single-quoted literal" in text
    assert "escape every literal single quote" in text
    assert "use a here-doc" in text
    assert "OBJECTIVE_RAW='__OBJECTIVE_SINGLE_QUOTED_PLACEHOLDER__'" in text
    assert "replace the objective single-quoted placeholder before running paired mode Step 2c" in text
    assert "printf '%s' \"$OBJECTIVE_RAW\" > \"$RENDER_DIR/objective\"" in text
    assert "Do not rely" in text
    assert "$OBJECTIVE` shell variable" in text
    assert "LIFELINE_OBJECTIVE_RAW" not in text
    assert "printf '%s' \"$OBJECTIVE\"" not in text
    assert "failed to create render dir" in text
    assert "failed to write objective file" in text


def test_paired_render_input_writes_fail_loudly() -> None:
    text = PAIRED_MODE.read_text()

    for name in ("git_diff_head", "untracked", "git_status", "files_touched"):
        assert f"> \"$RENDER_DIR/{name}\" ||" in text
        assert f"ERROR: failed to write render input {name}" in text


def test_paired_files_touched_has_path_allowlist() -> None:
    paired = PAIRED_MODE.read_text()
    prompt = (REPO_ROOT / "skills/deliver/references/grader-prompt.md").read_text()

    assert "_validated_files_touched=" in paired
    assert "skipping unsafe FILES_TOUCHED path" in paired
    assert "skipping FILES_TOUCHED path outside repo/tmp allowlist" in paired
    assert '*"/../"*|../*|*/..|..|~*|/etc/*|/proc/*|/sys/*|/dev/*|/run/secrets/*|*.env*|*.pem|*.key|.ssh/*|*/.ssh/*|.aws/*|*/.aws/*|*id_rsa*|*id_ed25519*' in paired
    assert '"$PWD"/*|./*|[!/]*)' in paired
    assert "/tmp/*|/var/tmp/*" in paired
    assert "drops `..`, system/secrets prefixes" in prompt


def test_budget_limit_instructions_list_actual_placeholders() -> None:
    pure = PURE_MODE.read_text()
    paired = PAIRED_MODE.read_text()

    for text in (pure, paired):
        assert "substitute only the placeholders that file contains" in text
        assert "`{{ objective }}`" in text
        assert "`{{ iter_used }}`" in text
        assert "`{{ iter_budget }}`" in text
        assert "substitute the same placeholders as 2a" not in text


def test_pure_mode_preflights_continuation_template() -> None:
    text = PURE_MODE.read_text()

    assert '[ -f "$SKILL_DIR/references/continuation.md" ] ||' in text
    assert "continuation.md not found" in text
    assert '[ -f "$SKILL_DIR/references/budget_limit.md" ] ||' in text
    assert "budget_limit.md not found" in text


def test_pure_mode_computes_escaped_objective_once() -> None:
    text = PURE_MODE.read_text()

    assert "single-quoted literal" in text
    assert "escape every literal single quote" in text
    assert "use a here-doc" in text
    assert "OBJECTIVE_RAW='__OBJECTIVE_SINGLE_QUOTED_PLACEHOLDER__'" in text
    assert "replace the objective single-quoted placeholder before running pure mode Step 1" in text
    assert "sed -e 's/&/\\&amp;/g' -e 's/</\\&lt;/g' -e 's/>/\\&gt;/g'" in text
    assert 'OBJECTIVE_HTML_DELIM="LIFELINE_OBJECTIVE_HTML<$(date +%s):$$>"' in text
    assert "OBJECTIVE_HTML cannot" in text
    assert "printf 'OBJECTIVE_HTML<<%s\\n'" in text
    assert "captured `OBJECTIVE_HTML`" in text
    assert "do not substitute the raw `$OBJECTIVE`" in text


def test_paired_mode_computes_escaped_objective_once() -> None:
    text = PAIRED_MODE.read_text()

    assert "single-quoted literal" in text
    assert "escape every literal single quote" in text
    assert "use a here-doc" in text
    assert "OBJECTIVE_RAW='__OBJECTIVE_SINGLE_QUOTED_PLACEHOLDER__'" in text
    assert "replace the objective single-quoted placeholder before running paired mode Step 1" in text
    assert "sed -e 's/&/\\&amp;/g' -e 's/</\\&lt;/g' -e 's/>/\\&gt;/g'" in text
    assert 'OBJECTIVE_HTML_DELIM="LIFELINE_OBJECTIVE_HTML<$(date +%s):$$>"' in text
    assert "OBJECTIVE_HTML cannot" in text
    assert "printf 'OBJECTIVE_HTML<<%s\\n'" in text
    assert "captured `OBJECTIVE_HTML`" in text
    assert "do not substitute the raw `$OBJECTIVE`" in text


def test_objective_capture_avoids_heredoc_delimiters() -> None:
    pure = PURE_MODE.read_text()
    paired = PAIRED_MODE.read_text()

    for text in (pure, paired):
        assert "OBJECTIVE_RAW=$(cat <<" not in text
        assert "OBJECTIVE_DELIM" not in text
        assert "__OBJECTIVE_DELIM_PLACEHOLDER__" not in text
    assert 'cat > "$RENDER_DIR/objective" <<' not in paired


def test_paired_mode_uses_timeout_command_array() -> None:
    text = PAIRED_MODE.read_text()

    assert "TIMEOUT_PREFIX" not in text
    assert "TIMEOUT_CMD=(timeout 300)" in text
    assert "TIMEOUT_CMD=()" in text
    assert '"${TIMEOUT_CMD[@]}" codex exec' in text


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

    assert "captured `OBJECTIVE_HTML`" in pure
    assert "captured `OBJECTIVE_HTML`" in paired
    assert "HTML-escaped `$OBJECTIVE`" not in paired
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


def test_resolver_mirrors_have_explicit_boundary_sentinels() -> None:
    assert "# BEGIN RESOLVER" in PURE_MODE.read_text()
    assert "# BEGIN RESOLVER" in PAIRED_MODE.read_text()
    assert "# BEGIN RESOLVER" in RESOLVER_SCRIPT.read_text()
    assert "# END RESOLVER" in PURE_MODE.read_text()
    assert "# END RESOLVER" in PAIRED_MODE.read_text()
    assert "# END RESOLVER" in RESOLVER_SCRIPT.read_text()


def test_mode_initialization_echoes_resolved_skill_dir_after_resolver() -> None:
    for path in (PURE_MODE, PAIRED_MODE):
        text = path.read_text()
        end_marker = text.find("# END RESOLVER")
        assert end_marker != -1, f"{path.name} missing # END RESOLVER"
        after_resolver = text[end_marker:]

        assert 'echo "SKILL_DIR=$SKILL_DIR"' in after_resolver


def test_resolver_script_emits_skill_dir_assignment() -> None:
    text = RESOLVER_SCRIPT.read_text()

    assert "Prints SKILL_DIR=<resolved path> to stdout" in text
    assert "printf 'SKILL_DIR=%s\\n'" in text
    assert "printf '%s\\n' \"$LIFELINE_SKILL_DIR\"" not in text


def test_resolver_script_validity_check_matches_inline_empty_path_behavior() -> None:
    text = RESOLVER_SCRIPT.read_text()

    assert '${1:-}' not in text
    assert '[ -f "$1/schemas/grader-output.json" ]' in text


def test_apache_license_text_is_distributed_with_notice() -> None:
    notice = NOTICE.read_text()
    license_text = APACHE_LICENSE.read_text()

    assert "LICENSE-apache-2.0" in notice
    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text
    assert "END OF TERMS AND CONDITIONS" in license_text


def test_smoke_tests_section_points_to_existing_guards() -> None:
    text = SKILL.read_text()

    assert "docs/superpowers/specs" not in text
    assert "python3 -m pytest -q harness/test_deliver_resolver_mirrors.py harness/test_deliver_skill_contracts.py" in text
    assert "python -m pytest" not in text
    assert "harness/test_deliver_resolver_mirrors.py" in text
    assert "harness/test_deliver_skill_contracts.py" in text
    assert ".github/workflows/deliver-guards.yml" in text


def test_paired_files_touched_is_escaped_and_grader_decodes_path_hints() -> None:
    paired = PAIRED_MODE.read_text()
    prompt = (REPO_ROOT / "skills/deliver/references/grader-prompt.md").read_text()

    assert "'{{ files_touched }}':   safe(f\"{d}/files_touched\")" in paired
    assert "'{{ files_touched }}':   read_text(f\"{d}/files_touched\")" not in paired
    assert "including `files_touched`, are HTML-encoded" in prompt
    assert "HTML-decode each path once before running `cat`, `ls`, or `head`" in prompt
    assert "not the `&lt;`, `&gt;`, or `&amp;` entity text" in prompt
    assert "opaque path hint" in prompt


def test_paired_incomplete_grader_verdict_requires_missing_requirements() -> None:
    paired = PAIRED_MODE.read_text()
    prompt = (REPO_ROOT / "skills/deliver/references/grader-prompt.md").read_text()

    assert (
        "and (if (.complete | not) then (.missing_requirements | length) > 0 else true end)"
        in paired
    )
    assert "complete:false implies" in paired
    assert 'MUST contain at least one entry when `complete: false`' in prompt
