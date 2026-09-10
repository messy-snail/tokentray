"""Reject release tags that do not match the package's version source."""

import ast
import os
from pathlib import Path


def check_version(ref: str, source: Path) -> None:
    if not ref.startswith("refs/tags/"):
        return  # Manual branch builds only validate artifacts; they do not publish.
    module = ast.parse(source.read_text(encoding="utf-8"))
    version = next(
        ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)
    )
    expected = f"refs/tags/v{version}"
    if ref != expected:
        raise ValueError(f"Release tag {ref!r} does not match package version: expected {expected!r}")


if __name__ == "__main__":
    check_version(
        os.environ["GITHUB_REF"],
        Path(__file__).resolve().parents[1] / "src/tokentray/__init__.py",
    )
