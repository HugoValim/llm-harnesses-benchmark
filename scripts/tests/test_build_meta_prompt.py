"""Tests for meta-analysis prompt interpolation and rollup injection."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_meta import build_meta_prompt  # noqa: E402
from benchmark.audit_report import DimensionScore, ParsedReport  # noqa: E402
from benchmark.audit_rollup import (  # noqa: E402
    build_aggregated_runs_ranking_table,
    build_all_runs_ranking_table,
    build_executive_summary_skeleton,
    build_model_coverage_table,
    build_ollama_model_ranking_table,
    build_precomputed_rollup,
    expected_section2_run_rows,
    executive_summary_expectations,
    model_harness_coverage,
    validate_meta_analysis_coverage,
    validate_meta_analysis_executive_summary,
    validate_meta_analysis_ollama_ranking,
    _cross_harness_cohort_slugs,
    _dimension_labels,
    _harness_section,
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
    assert "Executive summary skeleton" in rollup
    assert "Aggregated runs ranking" in rollup
    assert "All runs ranking (detail)" in rollup
    assert "All runs ranking (detail)" in prompt
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


def test_validate_meta_analysis_coverage_detects_total_mismatch(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "auditor_a"
    input_dir.mkdir()
    totals = {"claude": 80, "codex": 81, "opencode": 82}
    for harness, total in totals.items():
        target = input_dir / f"{harness}-glm_5_1_ollama_cloud"
        target.mkdir()
        (target / "report.md").write_text(
            "\n".join(
                [
                    "C. **Total score / 100**",
                    "",
                    f"**{total} / 100**",
                ]
            )
        )

    meta = tmp_path / "meta-analysis.md"
    meta.write_text(
        "\n".join(
            [
                "## 2. Best model overall",
                "",
                "| Rank | Harness | Model slug | Total | Tier |",
                "|---:|---|---|---:|---|",
                "| 1 | opencode | glm_5_1_ollama_cloud | 82 | B |",
                "| 2 | codex | glm_5_1_ollama_cloud | 80 | B |",
                "| 3 | claude | glm_5_1_ollama_cloud | 80 | B |",
            ]
        )
    )
    errors = validate_meta_analysis_coverage(meta, source_dirs=[input_dir])
    assert len(errors) == 1
    assert "row 2" in errors[0]
    assert "codex/glm_5_1_ollama_cloud=81" in errors[0]
    assert "80" in errors[0]


def test_build_all_runs_ranking_table_lists_every_run() -> None:
    def row(harness: str, slug: str, total: int) -> ParsedReport:
        return ParsedReport(
            auditor="auditor_a",
            target=f"{harness}-{slug}",
            harness=harness,
            model_slug=slug,
            total=total,
            tier="A" if total >= 81 else "B",
            dimensions=[
                DimensionScore(i, f"D{i}", 5, 10) for i in range(1, 11)
            ],
        )

    reports = [
        row("codex", "codex_gpt_5_5", 86),
        row("claude", "claude_opus_4_7", 82),
        row("cursor", "composer_2_5", 83),
        row("opencode", "glm_5_1_ollama_cloud", 88),
        row("codex", "glm_5_1_ollama_cloud", 84),
    ]
    table = build_all_runs_ranking_table(reports)
    assert "All runs ranking (detail)" in table
    assert "| 1 | opencode | glm_5_1_ollama_cloud | - | 88.0 | A |" in table
    assert "| 2 | codex | codex_gpt_5_5 | - | 86.0 | A |" in table
    assert "| 3 | codex | glm_5_1_ollama_cloud | - | 84.0 | A |" in table
    assert "| 4 | cursor | composer_2_5 | - | 83.0 | A |" in table
    assert "| 5 | claude | claude_opus_4_7 | - | 82.0 | A |" in table


def test_aggregated_runs_ranking_averages_replicates() -> None:
    reports = [
        ParsedReport(
            auditor="auditor",
            target="codex-demo/run_01",
            harness="codex",
            model_slug="demo",
            replicate_id="run_01",
            total=70,
        ),
        ParsedReport(
            auditor="auditor",
            target="codex-demo/run_02",
            harness="codex",
            model_slug="demo",
            replicate_id="run_02",
            total=80,
        ),
    ]
    table = build_aggregated_runs_ranking_table(reports)
    assert "Aggregated runs ranking" in table
    assert "| 1 | codex | demo | 75.0 | 2 | 7.1 | B |" in table
    rows = expected_section2_run_rows(reports)
    assert rows == [("codex", "demo", 75.0)]


def test_harness_section_excludes_single_harness_models() -> None:
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

    reports = [
        row("codex", "codex_gpt_5_5", 86),
        row("claude", "claude_opus_4_7", 82),
        row("codex", "glm_5_1_ollama_cloud", 84),
        row("claude", "glm_5_1_ollama_cloud", 82),
        row("opencode", "glm_5_1_ollama_cloud", 88),
    ]
    cohort = _cross_harness_cohort_slugs(reports)
    assert cohort == frozenset({"glm_5_1_ollama_cloud"})

    dim_labels = _dimension_labels(reports)
    harness_block = "\n".join(_harness_section(reports, dim_labels))
    assert "| codex | 1 |" in harness_block
    assert "| claude | 1 |" in harness_block
    assert "| opencode | 1 |" in harness_block


def _reports_with_cursor() -> list[ParsedReport]:
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
        row("cursor", "composer_2_5", 83),
    ]


def test_cursor_excluded_from_harness_contest_rollups() -> None:
    reports = _reports_with_cursor()
    coverage = model_harness_coverage(reports)
    assert coverage["glm_5_1_ollama_cloud"]["harness_count"] == 3
    assert coverage["composer_2_5"]["harness_count"] == 0
    assert coverage["composer_2_5"]["cursor_runs"] == 1

    from benchmark.audit_rollup import (
        build_cursor_agent_models_table,
    )

    cursor_table = build_cursor_agent_models_table(reports)
    assert "composer_2_5" in cursor_table
    assert "Cursor agent models" in cursor_table

    dim_labels = _dimension_labels(reports)
    harness_block = "\n".join(_harness_section(reports, dim_labels))
    assert "cursor" not in harness_block.split("Harness comparison")[1].split("##")[0]
    assert "codex" in harness_block
    assert "claude" in harness_block
    assert "opencode" in harness_block


def test_precomputed_rollup_includes_cursor_table(tmp_path: Path) -> None:
    input_dir = tmp_path / "auditor_a"
    input_dir.mkdir()
    for harness, total in [
        ("claude", 82),
        ("codex", 84),
        ("opencode", 88),
        ("cursor", 83),
    ]:
        slug = (
            "glm_5_1_ollama_cloud"
            if harness != "cursor"
            else "composer_2_5"
        )
        target = input_dir / f"{harness}-{slug}"
        target.mkdir()
        (target / "report.md").write_text(
            "\n".join(
                [
                    "C. **Total score / 100**",
                    "",
                    f"**{total} / 100**",
                ]
            )
        )

    rollup = build_precomputed_rollup(source_dirs=[input_dir])
    assert "Cursor agent models" in rollup
    assert "composer_2_5" in rollup
    assert "| cursor |" not in rollup.split("## Harness comparison")[1].split(
        "## Cursor agent models"
    )[0]


def _ollama_row(harness: str, slug: str, total: int) -> ParsedReport:
    return ParsedReport(
        auditor="auditor_a",
        target=f"{harness}-{slug}",
        harness=harness,
        model_slug=slug,
        total=total,
        tier="A" if total >= 81 else "B",
        dimensions=[DimensionScore(i, f"D{i}", 5, 10) for i in range(1, 11)],
    )


def test_build_ollama_model_ranking_table_orders_by_cross_harness_mean() -> None:
    reports = [
        _ollama_row("claude", "deepseek_v4_pro_ollama_cloud", 71),
        _ollama_row("codex", "deepseek_v4_pro_ollama_cloud", 76),
        _ollama_row("opencode", "deepseek_v4_pro_ollama_cloud", 75),
        _ollama_row("claude", "glm_5_1_ollama_cloud", 63),
        _ollama_row("codex", "glm_5_1_ollama_cloud", 73),
        _ollama_row("opencode", "glm_5_1_ollama_cloud", 76),
        _ollama_row("claude", "gemma4_ollama_cloud", 58),
        _ollama_row("codex", "gemma4_ollama_cloud", 44),
    ]
    table = build_ollama_model_ranking_table(reports)
    assert "## Ollama model ranking" in table
    assert "| 1 | deepseek_v4_pro_ollama_cloud | 3 | 74.0 |" in table
    assert "| 2 | glm_5_1_ollama_cloud | 3 | 70.7 |" in table
    assert "deepseek_v4_pro_ollama_cloud" in table.split("Best open-source model")[1]


def test_build_ollama_model_ranking_excludes_single_harness_ollama() -> None:
    reports = [
        _ollama_row("claude", "deepseek_v4_pro_ollama_cloud", 71),
        _ollama_row("codex", "deepseek_v4_pro_ollama_cloud", 76),
        _ollama_row("codex", "partial_ollama_cloud", 80),
    ]
    table = build_ollama_model_ranking_table(reports)
    assert "partial_ollama_cloud" not in table
    assert "deepseek_v4_pro_ollama_cloud" in table


def test_build_precomputed_rollup_includes_ollama_ranking(tmp_path: Path) -> None:
    input_dir = tmp_path / "auditor_a"
    input_dir.mkdir()
    for harness, total in [("claude", 71), ("codex", 76), ("opencode", 75)]:
        target = input_dir / f"{harness}-deepseek_v4_pro_ollama_cloud"
        target.mkdir()
        (target / "report.md").write_text(
            "\n".join(
                [
                    "C. **Total score / 100**",
                    "",
                    f"**{total} / 100**",
                ]
            )
        )

    rollup = build_precomputed_rollup(source_dirs=[input_dir])
    assert "## Ollama model ranking" in rollup
    assert "deepseek_v4_pro_ollama_cloud" in rollup


def test_build_precomputed_rollup_includes_d9_subcheck(tmp_path: Path) -> None:
    run_root = tmp_path / "run_01"
    input_dir = run_root / "audit-reports" / "auditor_a"
    input_dir.mkdir(parents=True)
    target = input_dir / "codex-demo"
    target.mkdir()
    (target / "report.md").write_text(
        "\n".join(
            [
                "C. **Total score / 100**",
                "",
                "**70 / 100**",
            ]
        )
    )
    project = run_root / "projects" / "codex-demo" / "project"
    project.mkdir(parents=True)
    (project / "docker-compose.yml").write_text(
        "services:\n  web:\n    restart: unless-stopped\n"
    )
    (project / "settings.py").write_text("LOGGING = {}\n")

    rollup = build_precomputed_rollup(
        source_dirs=[input_dir],
        benchmark_projects_root=run_root / "projects",
    )
    assert "## D9 sub-check cohort" in rollup
    assert "D9.3 restart" in rollup


def test_validate_meta_analysis_ollama_ranking_detects_mismatch(
    tmp_path: Path,
) -> None:
    reports = [
        _ollama_row("claude", "deepseek_v4_pro_ollama_cloud", 71),
        _ollama_row("codex", "deepseek_v4_pro_ollama_cloud", 76),
        _ollama_row("opencode", "deepseek_v4_pro_ollama_cloud", 75),
    ]
    input_dir = tmp_path / "auditor_a"
    input_dir.mkdir()
    for report in reports:
        target = input_dir / report.target
        target.mkdir()
        (target / "report.md").write_text(
            "\n".join(
                [
                    "C. **Total score / 100**",
                    "",
                    f"**{int(report.total)} / 100**",
                ]
            )
        )

    meta = tmp_path / "meta-analysis.md"
    meta.write_text(
        "\n".join(
            [
                "## 2a. Open-source (Ollama) model ranking",
                "",
                "| Rank | Model slug | N harnesses | Avg total | Std dev | Tier | Claude | Codex | Opencode |",
                "|---:|---|---:|---:|---:|---|---:|---:|---:|",
                "| 1 | deepseek_v4_pro_ollama_cloud | 3 | 70.0 | 2.5 | B | 71 | 76 | 75 |",
            ]
        )
    )
    errors = validate_meta_analysis_ollama_ranking(meta, source_dirs=[input_dir])
    assert len(errors) == 1
    assert "section 2a row 1" in errors[0]
    assert "avg=74.0" in errors[0]


def _exec_summary_fixture_reports() -> list[ParsedReport]:
    reports = [
        _ollama_row("claude", "deepseek_v4_pro_ollama_cloud", 71),
        _ollama_row("codex", "deepseek_v4_pro_ollama_cloud", 76),
        _ollama_row("opencode", "deepseek_v4_pro_ollama_cloud", 75),
        _ollama_row("claude", "glm_5_1_ollama_cloud", 63),
        _ollama_row("codex", "glm_5_1_ollama_cloud", 73),
        _ollama_row("opencode", "glm_5_1_ollama_cloud", 76),
        ParsedReport(
            auditor="auditor_a",
            target="codex-codex_gpt_5_5",
            harness="codex",
            model_slug="codex_gpt_5_5",
            total=86,
            tier="A",
            dimensions=[DimensionScore(i, f"D{i}", 5, 10) for i in range(1, 11)],
        ),
    ]
    return reports


def test_build_executive_summary_skeleton_splits_peak_and_open_source() -> None:
    reports = _exec_summary_fixture_reports()
    skeleton = build_executive_summary_skeleton(reports)

    assert "**Best model overall**: `codex_gpt_5_5`" in skeleton
    assert "86.0/100 under `codex`" in skeleton
    assert "single-harness anchor" in skeleton
    assert "**Best open-source model overall**: `deepseek_v4_pro_ollama_cloud`" in skeleton
    assert "74.0/100 cross-harness avg" in skeleton
    assert "same as best model overall" not in skeleton.lower()


def test_executive_summary_expectations_track_distinct_verdicts() -> None:
    reports = _exec_summary_fixture_reports()
    expectations = executive_summary_expectations(reports)

    assert expectations["top_model_slug"] == "codex_gpt_5_5"
    assert expectations["top_model_total"] == 86.0
    assert expectations["best_ollama_slug"] == "deepseek_v4_pro_ollama_cloud"
    assert expectations["best_ollama_avg"] == 74.0


def test_build_precomputed_rollup_includes_executive_skeleton(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "auditor_a"
    input_dir.mkdir()
    for report in _exec_summary_fixture_reports():
        target = input_dir / report.target
        target.mkdir(parents=True, exist_ok=True)
        (target / "report.md").write_text(
            "\n".join(
                [
                    "C. **Total score / 100**",
                    "",
                    f"**{int(report.total)} / 100**",
                ]
            )
        )

    rollup = build_precomputed_rollup(source_dirs=[input_dir])
    assert "## Executive summary skeleton" in rollup
    assert rollup.index("Executive summary skeleton") < rollup.index("Model coverage")
    assert "codex_gpt_5_5" in rollup.split("Executive summary skeleton")[1].split(
        "Model coverage"
    )[0]


def test_validate_meta_executive_summary_accepts_matching_bullets(
    tmp_path: Path,
) -> None:
    reports = _exec_summary_fixture_reports()
    input_dir = tmp_path / "auditor_a"
    input_dir.mkdir()
    for report in reports:
        target = input_dir / report.target
        target.mkdir(parents=True, exist_ok=True)
        (target / "report.md").write_text(
            "\n".join(
                [
                    "C. **Total score / 100**",
                    "",
                    f"**{int(report.total)} / 100**",
                ]
            )
        )

    skeleton_lines = [
        line
        for line in build_executive_summary_skeleton(reports).splitlines()
        if line.startswith("- **")
    ]
    meta = tmp_path / "meta-analysis.md"
    meta.write_text(
        "\n".join(
            [
                "## 1. Executive summary",
                "",
                *skeleton_lines,
                "",
                "## 2. Best model overall",
            ]
        )
    )
    errors = validate_meta_analysis_executive_summary(meta, source_dirs=[input_dir])
    assert errors == []


def test_validate_meta_executive_summary_detects_missing_slug(
    tmp_path: Path,
) -> None:
    reports = _exec_summary_fixture_reports()
    input_dir = tmp_path / "auditor_a"
    input_dir.mkdir()
    for report in reports:
        target = input_dir / report.target
        target.mkdir(parents=True, exist_ok=True)
        (target / "report.md").write_text(
            "\n".join(
                [
                    "C. **Total score / 100**",
                    "",
                    f"**{int(report.total)} / 100**",
                ]
            )
        )

    meta = tmp_path / "meta-analysis.md"
    meta.write_text(
        "\n".join(
            [
                "## 1. Executive summary",
                "",
                "- **Best model overall**: `wrong_model` — 86.0/100 under `codex`.",
                "- **Best open-source model overall**: `deepseek_v4_pro_ollama_cloud` — 74.0/100 cross-harness avg across 3 contest harnesses.",
                "- **Best harness overall**: `codex` — 74.5/100 avg (N=2).",
            ]
        )
    )
    errors = validate_meta_analysis_executive_summary(meta, source_dirs=[input_dir])
    assert any("codex_gpt_5_5" in err for err in errors)


def test_validate_meta_executive_summary_detects_paragraph_format(
    tmp_path: Path,
) -> None:
    reports = _exec_summary_fixture_reports()
    input_dir = tmp_path / "auditor_a"
    input_dir.mkdir()
    for report in reports:
        target = input_dir / report.target
        target.mkdir(parents=True, exist_ok=True)
        (target / "report.md").write_text(
            "\n".join(
                [
                    "C. **Total score / 100**",
                    "",
                    f"**{int(report.total)} / 100**",
                ]
            )
        )

    meta = tmp_path / "meta-analysis.md"
    meta.write_text(
        "\n".join(
            [
                "## 1. Executive summary",
                "",
                "**Best model overall**: `codex_gpt_5_5` — 86.0/100 (`report.md:8`).",
            ]
        )
    )
    errors = validate_meta_analysis_executive_summary(meta, source_dirs=[input_dir])
    assert any("bullet list" in err for err in errors)
    assert any("report.md citations" in err for err in errors)
