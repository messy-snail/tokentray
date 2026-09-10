"""Ensure an incorrect tag cannot reach publication."""

import runpy
from pathlib import Path

import pytest

check_version = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/check_release_version.py")
)["check_version"]


@pytest.mark.parametrize("ref", ["refs/tags/v0.1.0", "refs/heads/dev"])
def test_matching_tag_or_manual_branch_build(tmp_path, ref):
    source = tmp_path / "version.py"
    source.write_text('__version__ = "0.1.0"', encoding="utf-8")
    check_version(ref, source)


@pytest.mark.parametrize("ref", ["refs/tags/v0.2.0", "refs/tags/v0.1.0rc1", "refs/tags/vlatest"])
def test_mismatched_tag_is_rejected(tmp_path, ref):
    source = tmp_path / "version.py"
    source.write_text('__version__ = "0.1.0"', encoding="utf-8")
    with pytest.raises(ValueError, match="does not match package version"):
        check_version(ref, source)
