"""Tests for meta-analysis prompt interpolation and rollup injection."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_meta import build_meta_prompt  # noqa: E402
from benchmark.audit_report import DimensionScore, ParsedReport  # noqa: E402
from benchmark.audit_rollup import (  # noqa: E402
    build_model_coverage_table,
    build_precomputed_rollup,
    model_harness_coverage,
    validate_meta_analysis_coverage,
)


def _sample_reports() -> list[ParsedReport]:
    def row(harness: str, slug: str, total: int) -> ParsedReport:
        return ParsedReport(
            auditor="auditor_a",
            target=f"{harness}-{slug}",
            harness=harness,
            model_slug=slug,
            total=total,
            dimensions=[
                DimensionScore(i, f"D{i}", 5, 10) for i in range(1, 11)
            ],
        )

    return [
        row("claude", "glm_5_1_ollama_cloud", 82),
        row("codex", "glm_5_1_ollama_cloud", 84),
        row("opencode", "glm_5_1_ollama_cloud", 88),
        row("claude", "gemma4_ollama_cloud", 76),
        row("codex", "gemma4_ollama_cloud", 65),
        row("opencode", "gemma4_ollama_cloud", 75),
    ]


def test_model_harness_coverage_counts_all_harnesses() -> None:
    coverage = model_harness_coverage(_sample_reports())
    glm = coverage["glm_5_1_ollama_cloud"]
    assert glm["harness_count"] == 3
    assert glm["harnesses"] == ["claude", "codex", "opencode"]
    assert glm["runs"] == 3


def test_build_model_coverage_table_lists_glm_harnesses() -> None:
    table = build_model_coverage_table(_sample_reports())
    assert "glm_5_1_ollama_cloud" in table
    assert "claude, codex, opencode" in table
    assert "| 3 |" in table


def test_build_meta_prompt_includes_precomputed_rollup(tmp_path: Path) -> None:
    input_dir = tmp_path / "auditor_a"
    input_dir.mkdir()
    for harness, total in [("claude", 82), ("codex", 84), ("opencode", 88)]:
        target = input_dir / f"{harness}-glm_5_1_ollama_cloud"
        target.mkdir()
        (target / "report.md").write_text(
            "\n".join(
                [
                    "| 1 | D1 | 10/15 | ok |",
                    "C. **Total score / 100**",
                    "",
                    f"**{total} / 100**",
                ]
            )
        )

    rollup = build_precomputed_rollup(source_dirs=[input_dir])
    prompt = build_meta_prompt(
        "dirs:\n{audit_input_dirs}\n\nrollup:\n{precomputed_rollup}\n\nout:{output_path}",
        audit_input_dirs=[input_dir],
        output_path=tmp_path / "meta-analysis.md",
        precomputed_rollup=rollup,
    )
    assert "Model coverage" in prompt
    assert "Harness CLI versions" in rollup
    assert "Harness CLI versions" in prompt
    assert "glm_5_1_ollama_cloud" in prompt
    assert "claude, codex, opencode" in prompt
    assert str((tmp_path / "meta-analysis.md").resolve()) in prompt


def test_build_precomputed_rollup_includes_harness_versions(tmp_path: Path) -> None:
    input_dir = tmp_path / "auditor_a"
    target = input_dir / "claude-glm_5_1_ollama_cloud"
    target.mkdir(parents=True)
    (target / "report.md").write_text(
        "\n".join(
            [
                "C. **Total score / 100**",
                "",
                "**80 / 100**",
            ]
        )
    )
    (target / "generation-metrics.json").write_text(
        '{"harness_cli_version": "claude 2.0.0", "harness": "claude"}'
    )
    rollup = build_precomputed_rollup(source_dirs=[input_dir])
    assert "claude 2.0.0" in rollup
    assert "mixed-version" not in rollup or "Notes" in rollup


def test_validate_meta_analysis_coverage_detects_undercount(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "auditor_a"
    input_dir.mkdir()
    for harness in ("claude", "codex", "opencode"):
        target = input_dir / f"{harness}-glm_5_1_ollama_cloud"
        target.mkdir()
        (target / "report.md").write_text(
            "\n".join(
                [
                    "C. **Total score / 100**",
                    "",
                    "**80 / 100**",
                ]
            )
        )

    meta = tmp_path / "meta-analysis.md"
    meta.write_text(
        "\n".join(
            [
                "### 2. Best model overall",
                "",
                "| Rank | Model slug | Harnesses seen | Avg total |",
                "|---:|---|---:|---:|",
                "| 1 | glm_5_1_ollama_cloud | 2 | 80 |",
            ]
        )
    )
    errors = validate_meta_analysis_coverage(meta, source_dirs=[input_dir])
    assert len(errors) == 1
    assert "glm_5_1_ollama_cloud" in errors[0]
    assert "2 harnesses" in errors[0]
    assert "3" in errors[0]
