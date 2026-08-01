"""T6 — Supply-chain compromise of a dependency (security_architecture.md
§4/§10). Real defense exercised here: dependency pinning via `uv.lock` +
`uv sync --frozen`/`uv lock --check` (§10's own table) — the real gate
this project's own CI runs, not a re-implementation of it.

Two real, non-mocked proofs, both invoking the actual `uv` binary:

1. The real, currently-committed lockfile against the real, currently-
   committed manifests is genuinely reproducible right now — the same
   command this session verified manually ("Resolved 99 packages", exit
   0) run fresh, as an enforced regression guard rather than a one-off.
2. A real drift attempt — a dependency manifest edited without
   regenerating its lockfile (exactly what a compromised or careless
   commit could do) — is genuinely detected and refused by the same
   real tool, in a fully isolated, network-free temp project so the
   attempt never touches this repository's own lockfile.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_FALLBACK_UV = Path(
    "C:/Users/rahul/AppData/Roaming/Python/Python314/Scripts/uv.exe"
)  # documented environment quirk (CLAUDE.md): uv sync --frozen can remove uv from PATH


def _uv() -> str:
    found = shutil.which("uv")
    if found is not None:
        return found
    if _FALLBACK_UV.is_file():
        return str(_FALLBACK_UV)
    pytest.skip("uv is not available on PATH or at the documented fallback location")


def test_the_real_committed_lockfile_is_genuinely_reproducible_right_now() -> None:
    """The real, load-bearing check: does today's actual `uv.lock`
    genuinely match today's actual manifests? A `pyproject.toml` edited
    without a matching `uv lock` run is exactly how an unreviewed or
    compromised dependency change would first surface."""
    result = subprocess.run(  # noqa: S603 -- fixed argv, no shell, no untrusted input
        [_uv(), "lock", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, (
        f"the real, committed lockfile has drifted from the real, committed "
        f"manifests:\nstdout={result.stdout}\nstderr={result.stderr}"
    )


def test_a_real_drift_attempt_is_genuinely_detected_and_refused(tmp_path: Path) -> None:
    """A real attempt at the threat: a manifest is changed but its
    lockfile is not regenerated. Run in a fully isolated, dependency-free
    temp project (never touching this repo's own lockfile) so the
    real `uv` binary can be exercised offline, deterministically."""
    uv = _uv()
    project = tmp_path / "isolated_supply_chain_check"
    project.mkdir()
    pyproject = project / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "supply-chain-check"\nversion = "0.1.0"\n'
        'requires-python = ">=3.12"\ndependencies = []\n',
        encoding="utf-8",
    )

    lock_result = subprocess.run(  # noqa: S603 -- fixed argv, no shell, no untrusted input
        [uv, "lock"], cwd=project, capture_output=True, text=True, timeout=60
    )
    assert lock_result.returncode == 0, lock_result.stderr

    clean_check = subprocess.run(  # noqa: S603 -- fixed argv, no shell, no untrusted input
        [uv, "lock", "--check"], cwd=project, capture_output=True, text=True, timeout=60
    )
    assert clean_check.returncode == 0

    # The real drift: the manifest changes, the lockfile does not.
    pyproject.write_text(
        '[project]\nname = "supply-chain-check"\nversion = "0.2.0"\n'
        'requires-python = ">=3.12"\ndependencies = []\n',
        encoding="utf-8",
    )

    drifted_check = subprocess.run(  # noqa: S603 -- fixed argv, no shell, no untrusted input
        [uv, "lock", "--check"], cwd=project, capture_output=True, text=True, timeout=60
    )

    assert drifted_check.returncode != 0
    assert "lockfile" in drifted_check.stderr.lower()
