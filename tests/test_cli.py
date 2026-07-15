from __future__ import annotations

import subprocess
from pathlib import Path

from materialai_qa.cli import _product_commit


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def test_product_commit_does_not_inherit_parent_repository(tmp_path: Path) -> None:
    repo = tmp_path / "qa-repository"
    product_root = repo / "evidence" / "downloaded-product"
    product_root.mkdir(parents=True)
    _run_git(repo, "init")
    (repo / "README.md").write_text("QA fixture\n", encoding="utf-8")
    _run_git(repo, "add", "README.md")
    _run_git(
        repo,
        "-c",
        "user.name=MaterialAI QA",
        "-c",
        "user.email=qa@example.invalid",
        "commit",
        "-m",
        "Initialize QA fixture",
    )

    assert _product_commit(product_root) is None


def test_product_commit_reads_exact_repository_root(tmp_path: Path) -> None:
    product_root = tmp_path / "product"
    product_root.mkdir()
    _run_git(product_root, "init")
    (product_root / "README.md").write_text("Product fixture\n", encoding="utf-8")
    _run_git(product_root, "add", "README.md")
    _run_git(
        product_root,
        "-c",
        "user.name=MaterialAI QA",
        "-c",
        "user.email=qa@example.invalid",
        "commit",
        "-m",
        "Initialize product fixture",
    )
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=product_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert _product_commit(product_root) == expected
