"""Regression tests for the /lifeline:deliver skill-dir resolver mirrors."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PURE_MODE = REPO_ROOT / "skills/deliver/references/pure-mode.md"
PAIRED_MODE = REPO_ROOT / "skills/deliver/references/paired-mode.md"
RESOLVER_SCRIPT = REPO_ROOT / "skills/deliver/scripts/resolve-skill-dir.sh"


def _resolver_bash_block(path: Path) -> str:
    text = path.read_text()
    marker = "# MIRROR OF skills/deliver/scripts/resolve-skill-dir.sh"
    marker_at = text.find(marker)
    assert marker_at != -1, f"{path} is missing the resolver mirror marker"
    start = text.find('SKILL_DIR=""', marker_at)
    assert start != -1, f"{path} is missing SKILL_DIR initialization after marker"
    end = text.find("\n# END RESOLVER", start)
    assert end != -1, f"{path} is missing the resolver end marker"
    return text[start:end].rstrip() + '\n\necho "SKILL_DIR=$SKILL_DIR"\n'


RESOLVERS = {
    "pure-mode.md inline block": ("inline", PURE_MODE),
    "paired-mode.md inline block": ("inline", PAIRED_MODE),
    "resolve-skill-dir.sh": ("script", RESOLVER_SCRIPT),
}


def test_inline_resolver_extraction_excludes_surrounding_initialization() -> None:
    pure = _resolver_bash_block(PURE_MODE)
    paired = _resolver_bash_block(PAIRED_MODE)

    assert "ITER=0" not in pure
    assert 'echo "SKILL_DIR=' in pure
    assert "SCHEMA_PATH=" not in pure
    assert "mktemp" not in pure

    assert "SCHEMA_PATH=" not in paired
    assert "GRADER_TEMPLATE=" not in paired
    assert 'echo "SKILL_DIR=' in paired
    assert "command -v jq" not in paired
    assert "command -v python3" not in paired
    assert "mktemp" not in paired


def _make_deliver_skill(path: Path) -> Path:
    (path / "schemas").mkdir(parents=True)
    (path / "schemas/grader-output.json").write_text("{}\n")
    (path / "references").mkdir(parents=True)
    (path / "references/grader-prompt.md").write_text("grader\n")
    return path


def _fake_tool(path: Path) -> None:
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _base_env(tmp_path: Path) -> dict[str, str]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir(exist_ok=True)
    # The paired-mode block checks these tools before it allocates scratch.
    # The resolver tests do not need the real binaries.
    _fake_tool(fake_bin / "jq")
    _fake_tool(fake_bin / "python3")

    env = os.environ.copy()
    env["HOME"] = str(tmp_path / "home")
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
    env["TMPDIR"] = str(tmp_path)
    env.pop("LIFELINE_SKILL_DIR", None)
    return env


def _run_resolver(
    kind: str,
    source: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    if kind == "inline":
        cmd = ["bash", "-c", _resolver_bash_block(source)]
    else:
        cmd = [str(source)]

    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
    )

    return proc


def _value_from_output(stdout: str, key: str) -> str | None:
    prefix = f"{key}="
    for line in stdout.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :]
    return None


def _resolved_skill_dir(proc: subprocess.CompletedProcess[str]) -> str:
    skill_dir = _value_from_output(proc.stdout, "SKILL_DIR")
    if skill_dir is not None:
        return skill_dir

    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert lines, f"resolver produced no stdout; stderr was:\n{proc.stderr}"
    return lines[-1]


@pytest.mark.parametrize("name, resolver", RESOLVERS.items())
def test_deliver_resolver_mirrors_accept_env_override(
    tmp_path: Path,
    name: str,
    resolver: tuple[str, Path],
) -> None:
    """All three resolver copies must honor LIFELINE_SKILL_DIR first."""
    skill_dir = _make_deliver_skill(tmp_path / "local-deliver")
    env = _base_env(tmp_path)
    env["LIFELINE_SKILL_DIR"] = str(skill_dir)

    proc = _run_resolver(*resolver, env=env)

    assert proc.returncode == 0, (
        f"{name} failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert _resolved_skill_dir(proc) == str(skill_dir)


@pytest.mark.parametrize("name, resolver", RESOLVERS.items())
def test_deliver_resolver_mirrors_pick_newest_cache_directory_and_ignore_files(
    tmp_path: Path,
    name: str,
    resolver: tuple[str, Path],
) -> None:
    """Mirror guard for cache ordering and the macOS .DS_Store failure mode."""
    env = _base_env(tmp_path)
    cache_root = Path(env["HOME"]) / ".claude/plugins/cache/lifeline/lifeline"
    _make_deliver_skill(cache_root / "old/skills/deliver")
    new_skill = _make_deliver_skill(cache_root / "new/skills/deliver")
    ds_store = cache_root / ".DS_Store"
    ds_store.write_text("finder metadata\n")

    os.utime(cache_root / "old", (1000, 1000))
    os.utime(cache_root / "new", (2000, 2000))
    os.utime(ds_store, (3000, 3000))

    proc = _run_resolver(*resolver, env=env)

    assert proc.returncode == 0, (
        f"{name} failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert _resolved_skill_dir(proc) == str(new_skill)


@pytest.mark.parametrize("name, resolver", RESOLVERS.items())
def test_deliver_resolver_mirrors_do_not_fall_back_to_workspace(
    tmp_path: Path,
    name: str,
    resolver: tuple[str, Path],
) -> None:
    """Workspace lookup was removed for security; all mirrors must keep it out."""
    env = _base_env(tmp_path)

    proc = _run_resolver(*resolver, env=env)

    assert proc.returncode != 0, (
        f"{name} unexpectedly resolved from workspace:\n{proc.stdout}"
    )
    assert "could not resolve" in proc.stderr.lower()
