"""Tests for review module — parsing and validation."""

import pytest

from review import _build_local_review_cmd, parse_codex_output, parse_cloud_review_comment


def test_build_local_review_cmd_no_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default: omit --model so codex picks the auth-mode-correct default."""
    monkeypatch.delenv("LIFELINE_CODEX_MODEL", raising=False)
    cmd = _build_local_review_cmd("main")
    assert cmd == ["codex", "exec", "review", "--base", "main", "--full-auto"]
    assert "--model" not in cmd


def test_build_local_review_cmd_with_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    """LIFELINE_CODEX_MODEL set: append --model <value>."""
    monkeypatch.setenv("LIFELINE_CODEX_MODEL", "gpt-5.4")
    cmd = _build_local_review_cmd("develop")
    assert cmd == [
        "codex", "exec", "review",
        "--base", "develop",
        "--full-auto",
        "--model", "gpt-5.4",
    ]


def test_build_local_review_cmd_blank_pin_treated_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Whitespace-only env value should not produce an empty --model arg."""
    monkeypatch.setenv("LIFELINE_CODEX_MODEL", "   ")
    cmd = _build_local_review_cmd("main")
    assert "--model" not in cmd


def test_parse_codex_output_no_findings():
    output = """OpenAI Codex v0.114.0
--------
codex
No actionable issues were found."""
    result = parse_codex_output(output)
    assert result["has_findings"] is False
    assert result["findings"] == []


def test_parse_codex_output_with_findings():
    output = """thinking
**Found issue**
Some thinking text
codex
Found 2 issues:
1. [HIGH] Missing error handling in src/app.ts:42
   The function does not handle the error case.
2. [MEDIUM] Unused import in src/utils.ts:1
   Remove unused import."""
    result = parse_codex_output(output)
    assert result["has_findings"] is True
    assert result["raw_review"] != ""


def test_parse_cloud_review_comment_json():
    body = '''## Codex Code Review

### 🟠 [HIGH] Missing error handling

📍 `src/app.ts` L42-45
🎯 Confidence: 85%

The function does not handle the error case.

---

**Overall: ⚠️ patch has issues** (confidence: 78%)

> One maintainability issue found.'''
    result = parse_cloud_review_comment(body)
    assert result["has_findings"] is True
    assert "Missing error handling" in result["raw_review"]


def test_parse_cloud_review_comment_clean():
    body = '''## Codex Code Review

✅ No issues found.

**Overall: ✅ patch is correct** (confidence: 92%)

> No issues introduced by the diff.'''
    result = parse_cloud_review_comment(body)
    assert result["has_findings"] is False
