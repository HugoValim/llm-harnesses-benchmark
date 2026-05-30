"""AI-backed meta-analysis dispatch.

Reads every audit ``report.md`` under one or more auditor-scoped directories
and dispatches a configured LLM to produce ``meta-analysis.md`` with
best-harness / best-model / cost / dimension verdicts.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from benchmark.result_layout import HARNESS_PREFIXES
from benchmark.timeouts import (
    DEFAULT_NO_PROGRESS_TIMEOUT_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
)
from benchmark.rate_limit import RateLimitWaitPolicy

if TYPE_CHECKING:  # pragma: no cover
    pass


def audit_model_harness(
    config: dict, slug: str, models_config: dict | None = None
) -> str:
    """Return the first registry harness containing model slug.

    Falls back to auto-derived routing for ollama_cloud models: those are
    auto-included in the claude harness without an explicit harnesses.json entry.
    """
    preferred = ["claude", "codex", "opencode", "cursor"]
    harnesses = preferred + [h for h in config if h not in preferred]
    for harness in harnesses:
        entry = config.get(harness)
        if not isinstance(entry, dict):
            continue
        models = entry.get("models")
        if isinstance(models, dict) and slug in models:
            return str(harness)
    if models_config is not None:
        from benchmark.config import _PROVIDER_HARNESS_MAP

        registry = models_config.get("models") or []
        _preferred = ["claude", "codex", "opencode", "cursor"]
        for model in registry:
            if not isinstance(model, dict) or model.get("slug") != slug:
                continue
            provider = model.get("provider", "")
            harnesses = _PROVIDER_HARNESS_MAP.get(provider, frozenset())
            if harnesses:
                return min(
                    harnesses,
                    key=lambda h: _preferred.index(h) if h in _preferred else 99,
                )
            if model.get("opencode_id"):
                return "opencode"
    raise ValueError(f"No harness model with slug={slug!r}")


def _meta_row_to_variant(model: dict) -> dict:
    variant = dict(model)
    main_model = variant.get("main_model") or variant.get("id")
    if not isinstance(main_model, str) or not main_model:
        raise ValueError(
            f"meta model row {variant.get('slug')!r} needs string id or main_model"
        )
    variant["main_model"] = main_model
    variant.setdefault("runner_type", variant.get("harness", "claude"))
    return variant


def _meta_config_variants(meta_config: dict) -> list[dict]:
    return [
        _meta_row_to_variant(model)
        for model in meta_config.get("models", [])
        if not model.get("skip_by_default")
    ]


def _meta_variant_harness(variant: dict) -> str:
    value = variant.get("harness") or variant.get("runner_type", "claude")
    return str(value)


def resolve_meta_variant(
    meta_config: dict, harness: str, model_slug: str | None
) -> dict:
    """Look up a meta-analysis model from models config.

    The config is a resolved harness-scoped model list:
    ``{"models": [{"slug": ..., "id": ..., "harness": ...}]}``.

    Selection rules:
    1. If ``model_slug`` is given, must match a model's slug exactly.
    2. Registry row ``harness`` must equal ``harness``.
    3. Otherwise the first non-skipped model with matching harness wins.

    Raises ``ValueError`` with a descriptive message on mismatch.
    """
    variants = _meta_config_variants(meta_config)
    matches_harness = [v for v in variants if _meta_variant_harness(v) == harness]
    if not matches_harness:
        if model_slug is not None and any(v["slug"] == model_slug for v in variants):
            raise ValueError(f"Slug `{model_slug}` is not a {harness} meta model.")
        available = ", ".join(
            sorted({_meta_variant_harness(v) for v in variants})
        ) or "(none)"
        raise ValueError(
            f"No meta-analysis model with harness={harness!r}. "
            f"Available harnesses in config: {available}."
        )
    if model_slug is None:
        return matches_harness[0]
    matches_slug = [v for v in matches_harness if v["slug"] == model_slug]
    if len(matches_slug) == 1:
        return matches_slug[0]
    if len(matches_slug) > 1:
        raise ValueError(
            f"Expected exactly one meta-analysis model with slug={model_slug!r} "
            f"under harness={harness!r}; found {len(matches_slug)}."
        )
    if any(v["slug"] == model_slug for v in variants):
        raise ValueError(f"Slug `{model_slug}` is not a {harness} meta model.")
    slugs = ", ".join(v["slug"] for v in matches_harness)
    raise ValueError(
        f"No meta-analysis model with slug={model_slug!r} under "
        f"harness={harness!r}. Available slugs: {slugs}."
    )


def discover_auditor_subdirs(reports_dir: Path) -> list[Path]:
    """Return the auditor subdirs under ``reports_dir`` that contain reports.

    An auditor subdir is a direct child directory of ``reports_dir`` that:
    - does not start with ``_`` (skips ``_meta-analysis-runs/``),
    - does not start with one of the harness prefixes (``claude-``,
      ``codex-``, ``opencode-``) — those are stray target outputs that
      ended up at the wrong nesting level and should not be globbed,
    - contains at least one ``*/report.md`` file (one report per audited target).

    Returns paths sorted by name. Empty list when ``reports_dir`` does
    not exist or contains no auditor-shaped subdirs.
    """
    if not reports_dir.is_dir():
        return []
    found: list[Path] = []
    for child in sorted(reports_dir.iterdir()):
        if not child.is_dir():
            continue
        name = child.name
        if name.startswith("_"):
            continue
        if any(name.startswith(f"{p}-") for p in HARNESS_PREFIXES):
            continue
        if not any(child.glob("**/report.md")):
            continue
        found.append(child)
    return found


def _render_audit_input_dirs(dirs: list[Path]) -> str:
    """Render a list of auditor subdirs as a markdown bullet list of absolute paths."""
    return "\n".join(f"- {p.resolve()}" for p in dirs)


def build_meta_prompt(
    template: str,
    *,
    audit_input_dirs: list[Path],
    output_path: Path,
    precomputed_rollup: str = "",
) -> str:
    """Interpolate the meta-analysis prompt template's placeholders.

    The template exposes ``{audit_input_dirs}`` (rendered as a markdown
    bullet list of auditor-scoped directories the meta-analyst must glob
    ``report.md`` files under), ``{precomputed_rollup}`` (harness-computed
    coverage and statistical summary), and ``{output_path}`` (where it must
    write ``meta-analysis.md``).
    """
    if not audit_input_dirs:
        raise ValueError("audit_input_dirs must be non-empty")
    return (
        template.replace(
            "{audit_input_dirs}", _render_audit_input_dirs(audit_input_dirs)
        )
        .replace("{precomputed_rollup}", precomputed_rollup.rstrip())
        .replace("{output_path}", str(output_path.resolve()))
    )


def run_ai_meta_analysis(
    *,
    reports_dir: Path,
    audit_input_dirs: list[Path],
    prompt_template: str,
    variant: dict,
    harness: str,
    runner_command_prefix: list[str] | None = None,
    isolate_home: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    no_progress_timeout_seconds: int = DEFAULT_NO_PROGRESS_TIMEOUT_SECONDS,
    force: bool = False,
    rate_limit_policy: RateLimitWaitPolicy | None = None,
    meta_runs_dir: Path | None = None,
    benchmark_projects_root: Path | None = None,
) -> dict:
    """Dispatch an LLM to write the meta-analysis markdown file.

    The LLM (selected by ``variant`` + ``harness``) is invoked via the
    Claude Code runner.

    Supported harnesses: ``"claude"``, ``"codex"``, ``"ollama"``.
    """
    if harness not in {"claude", "codex", "ollama"}:
        raise NotImplementedError(
            f"meta-analysis harness={harness!r} not supported; "
            "expected one of 'claude', 'codex', 'ollama'."
        )

    reports_dir = reports_dir.resolve()
    reports_dir.mkdir(parents=True, exist_ok=True)
    resolved_inputs: list[Path] = []
    for d in audit_input_dirs:
        rd = d.resolve()
        if not rd.is_dir():
            raise FileNotFoundError(
                f"audit input dir does not exist or is not a directory: {rd}"
            )
        resolved_inputs.append(rd)
    if not resolved_inputs:
        raise ValueError("audit_input_dirs must be non-empty")
    output_path = reports_dir / "meta-analysis.md"

    from benchmark.audit_rollup import build_precomputed_rollup  # noqa: PLC0415
    from benchmark.config import build_display_slug_map  # noqa: PLC0415

    display_slug_map = build_display_slug_map(
        Path(__file__).resolve().parents[2] / "config" / "models.json"
    )
    precomputed_rollup = build_precomputed_rollup(
        source_dirs=resolved_inputs,
        display_slug_map=display_slug_map,
        benchmark_projects_root=benchmark_projects_root,
    )
    prompt = build_meta_prompt(
        prompt_template,
        audit_input_dirs=resolved_inputs,
        output_path=output_path,
        precomputed_rollup=precomputed_rollup,
    )

    meta_runs_base = (meta_runs_dir if meta_runs_dir is not None else reports_dir).resolve()
    meta_run_dir = meta_runs_base / "_meta-analysis-runs" / variant["slug"]
    meta_run_dir.mkdir(parents=True, exist_ok=True)
    (meta_run_dir / "prompt.txt").write_text(prompt)

    if harness in {"codex", "ollama"}:
        from benchmark.runner import run_codex_variant  # noqa: PLC0415

        return run_codex_variant(
            variant=variant,
            prompt=prompt,
            results_dir=meta_run_dir.parent,
            timeout_seconds=timeout_seconds,
            no_progress_timeout_seconds=no_progress_timeout_seconds,
            force=force,
            harness=harness,
            explicit_result_dir=meta_run_dir,
            rate_limit_policy=rate_limit_policy,
        )

    from benchmark.claude_code_runner import run_variant  # noqa: PLC0415

    return run_variant(
        variant=variant,
        prompt=prompt,
        results_dir=meta_run_dir.parent,
        timeout_seconds=timeout_seconds,
        no_progress_timeout_seconds=no_progress_timeout_seconds,
        force=force,
        runner_command_prefix=runner_command_prefix,
        isolate_home=isolate_home,
        explicit_result_dir=meta_run_dir,
        rate_limit_policy=rate_limit_policy,
    )
