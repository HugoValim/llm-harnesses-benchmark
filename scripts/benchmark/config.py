"""Benchmark configuration loading and opencode config generation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from benchmark.backends import LocalModelBackend
from benchmark.rate_limit import RateLimitWaitPolicy
from benchmark.run_status import TERMINAL_STATUSES
from benchmark.workspace import summarize_project
from benchmark.util import (
    clone_json,
    load_json,
    load_optional_json,
    ollama_launch_command_prefix,
    print_line,
    save_json,
    save_json_preserve_order,
)


OPENCODE_CONFIG_PATH = Path.home() / ".config" / "opencode" / "opencode.json"

OPENCODE_YOLO_PERMISSION = {
    "bash": {"*": "allow"},
    "codesearch": {"*": "allow"},
    "doom_loop": {"*": "allow"},
    "edit": {"*": "allow"},
    "external_directory": {"*": "allow"},
    "glob": {"*": "allow"},
    "grep": {"*": "allow"},
    "list": {"*": "allow"},
    "lsp": {"*": "allow"},
    "read": {"*": "allow"},
    "skill": {"*": "allow"},
    "task": {"*": "allow"},
    "todowrite": {"*": "allow"},
    "webfetch": {"*": "allow"},
    "websearch": {"*": "allow"},
}

_OLLAMA_CLOUD_EXPAND_HARNESSES = frozenset({"claude", "codex", "opencode", "ollama"})


def _validate_ollama_cloud_harness(harness: str) -> None:
    if harness in _OLLAMA_CLOUD_EXPAND_HARNESSES:
        return
    raise ValueError(
        "expand_ollama_cloud_config: harness must be one of "
        f"{sorted(_OLLAMA_CLOUD_EXPAND_HARNESSES)}, got {harness!r}"
    )


def _require_ollama_cloud_object(config: dict[str, Any], key: str) -> dict[str, Any]:
    value = config.get(key)
    if isinstance(value, dict):
        return value
    raise ValueError(
        f"ollama_cloud config expects object {key}, got {type(value).__name__}"
    )


def _require_ollama_cloud_models(config: dict[str, Any]) -> list[dict[str, Any]]:
    value = config.get("models")
    if not isinstance(value, list):
        raise ValueError(
            "ollama_cloud config expects array models, "
            f"got {type(value).__name__}"
        )
    return [
        _validate_ollama_cloud_model_entry(i, entry)
        for i, entry in enumerate(value)
    ]


def _require_ollama_cloud_string(
    entry: dict[str, Any], index: int, key: str
) -> str:
    value = entry.get(key)
    if isinstance(value, str) and value:
        return value
    raise ValueError(
        f"ollama_cloud models[{index}] missing required string key {key!r}; "
        f"entry={entry!r}"
    )


def _validate_ollama_cloud_model_entry(index: int, entry: Any) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise ValueError(
            f"ollama_cloud models[{index}] must be object, "
            f"got {type(entry).__name__}: {entry!r}"
        )
    _require_ollama_cloud_string(entry, index, "slug")
    _require_ollama_cloud_string(entry, index, "id")
    _require_ollama_cloud_string(entry, index, "label")
    return entry


def _ollama_cloud_harness_key(harness: str) -> str:
    return "codex" if harness == "ollama" else harness


def _validate_ollama_cloud_runner_config(
    runner_configs: dict[str, Any], harness: str
) -> tuple[dict[str, Any], list[Any]]:
    harness_key = _ollama_cloud_harness_key(harness)
    rc = runner_configs.get(harness_key)
    if not isinstance(rc, dict):
        raise ValueError(
            f"ollama_cloud runner_configs missing key {harness_key!r} "
            f"(requested harness={harness!r})."
        )
    command_prefix = rc.get("command_prefix")
    if isinstance(command_prefix, list) and command_prefix:
        return rc, command_prefix
    raise ValueError(
        f"runner_configs[{harness_key!r}] needs non-empty list command_prefix, "
        f"got {command_prefix!r}"
    )


def _expand_ollama_cloud_claude_config(
    runner: dict[str, Any],
    command_prefix: list[Any],
    shared_models: list[dict[str, Any]],
) -> dict[str, Any]:
    variants = [
        {
            "slug": entry["slug"],
            "label": f"{entry['label']} via Claude Code",
            "main_model": entry["id"],
            "subagent": None,
            "command_prefix": list(command_prefix),
            "selection_reason": str(entry.get("selection_reason", "")),
        }
        for entry in shared_models
    ]
    return {"runner": runner, "variants": variants}


def _expand_ollama_cloud_models_config(
    runner: dict[str, Any],
    command_prefix: list[Any],
    shared_models: list[dict[str, Any]],
    harness: str,
) -> dict[str, Any]:
    via = "OpenCode" if harness == "opencode" else "Codex"
    models_out = [
        {
            "slug": entry["slug"],
            "id": entry["id"],
            "label": f"{entry['label']} via {via}",
            "provider": "ollama_cloud",
            "runner_type": harness,
            "command_prefix": list(command_prefix),
            "selection_reason": str(entry.get("selection_reason", "")),
        }
        for entry in shared_models
    ]
    return {"runner": runner, "models": models_out}


def expand_ollama_cloud_config(
    config: dict[str, Any], harness: str
) -> dict[str, Any]:
    """Expand legacy Ollama Cloud rows into a normal harness config dict.

    Unified rows list ``slug``, ``id`` (Ollama tag), ``label`` (without ``via …``),
    and ``selection_reason``; runner metadata lives under ``runner_configs``.
    """
    if not config.get("ollama_cloud"):
        return config
    _validate_ollama_cloud_harness(harness)
    runner_configs = _require_ollama_cloud_object(config, "runner_configs")
    shared_models = _require_ollama_cloud_models(config)
    rc, command_prefix = _validate_ollama_cloud_runner_config(runner_configs, harness)
    runner = {k: v for k, v in rc.items() if k != "command_prefix"}
    if harness == "claude":
        return _expand_ollama_cloud_claude_config(
            runner, command_prefix, shared_models
        )
    return _expand_ollama_cloud_models_config(
        runner, command_prefix, shared_models, harness
    )


def _validate_registry_model_num_runs(model: dict[str, Any]) -> int:
    """Require a positive integer ``num_runs`` on each registry model row."""
    slug = model.get("slug", "<unknown>")
    value = model.get("num_runs")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"models.json model {slug!r} requires positive integer num_runs, "
            f"got {value!r}"
        )
    if value < 1:
        raise ValueError(
            f"models.json model {slug!r} requires num_runs >= 1, got {value!r}"
        )
    return value


def _resolve_model_num_runs(model: dict[str, Any]) -> int:
    """Return configured ``num_runs``, defaulting inline/test rows to ``1``."""
    if "num_runs" not in model:
        return 1
    return _validate_registry_model_num_runs(model)


def _normalize_registry_models(models: Any) -> list[dict[str, Any]]:
    if not isinstance(models, list):
        return []
    out: list[dict[str, Any]] = []
    for model in models:
        if not isinstance(model, dict):
            continue
        row = clone_json(model)
        row["num_runs"] = _resolve_model_num_runs(row)
        out.append(row)
    return out


def registry_by_slug(models: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index registry model rows by ``slug``.

    Example:
        ``registry_by_slug(load_json(Path("config/models.json"))["models"])``
    """
    return {
        str(m["slug"]): m
        for m in models
        if isinstance(m, dict) and m.get("slug")
    }


def format_display_slug(
    slug: str,
    *,
    codex_reasoning_effort: str | None = None,
) -> str:
    """Return human-facing slug with Codex reasoning effort when configured."""
    if codex_reasoning_effort:
        return f"{slug}({codex_reasoning_effort})"
    return slug


def display_slug_for(registry: dict[str, dict[str, Any]], slug: str) -> str:
    """Look up ``slug`` in the registry and apply reasoning-effort annotation."""
    row = registry.get(slug, {})
    effort = row.get("codex_reasoning_effort")
    if isinstance(effort, str) and effort:
        return format_display_slug(slug, codex_reasoning_effort=effort)
    return slug


def build_display_slug_map(models_config: Path) -> dict[str, str]:
    """Build ``canonical_slug -> display_slug`` from ``config/models.json``."""
    payload = load_json(models_config)
    models = payload.get("models", [])
    if not isinstance(models, list):
        return {}
    registry = registry_by_slug(models)
    return {slug: display_slug_for(registry, slug) for slug in registry}


def _load_registry_harness(config_path: Path, harness: str) -> dict[str, Any]:
    harnesses_path = config_path.parent / "harnesses.json"
    if not harnesses_path.exists():
        raise ValueError(
            f"registry config {config_path!s} has no runner; expected harnesses at "
            f"{harnesses_path!s}"
        )
    harnesses = load_json(harnesses_path)
    runner = harnesses.get(harness)
    if isinstance(runner, dict):
        return runner
    raise ValueError(
        f"registry config {harnesses_path!s} missing harness {harness!r}; "
        f"available={sorted(harnesses)}"
    )


# Maps provider -> harnesses that run it natively (without opencode_id).
_PROVIDER_HARNESS_MAP: dict[str, frozenset[str]] = {
    "anthropic": frozenset({"claude"}),
    "openai": frozenset({"codex"}),
    "cursor": frozenset({"cursor"}),
    "ollama_cloud": frozenset({"claude", "codex", "opencode"}),
}


def _build_registry_model_row(model: dict[str, Any], harness: str) -> dict[str, Any]:
    row = clone_json(model)
    row["harness"] = harness
    # opencode uses a harness-specific id (e.g. openrouter path) when provided.
    if harness == "opencode" and model.get("opencode_id"):
        row["id"] = model["opencode_id"]
    provider = row.get("provider", "")
    if provider == "ollama_cloud":
        # codex: runner_type=ollama auto-injects `ollama launch codex`.
        # claude/opencode: per-model command_prefix for `ollama launch <harness>`.
        if harness == "codex":
            row.setdefault("runner_type", "ollama")
        else:
            row.setdefault("runner_type", harness)
            row.setdefault("command_prefix", ollama_launch_command_prefix(harness))
    elif provider == "openai":
        row.setdefault("runner_type", "codex")
    else:
        row.setdefault("runner_type", harness)
    if not isinstance(row.get("id"), str) or not row["id"]:
        raise ValueError(
            f"harness {harness!r} model {row.get('slug')!r} needs string id"
        )
    row["num_runs"] = _resolve_model_num_runs(row)
    return row


def _registry_models_for_harness(
    registry_models: list[dict[str, Any]], harness: str
) -> list[dict[str, Any]]:
    out = []
    for model in registry_models:
        provider = model.get("provider", "")
        if harness in _PROVIDER_HARNESS_MAP.get(provider, frozenset()):
            out.append(_build_registry_model_row(model, harness))
        elif harness == "opencode" and model.get("opencode_id"):
            out.append(_build_registry_model_row(model, harness))
    return out


def _strip_harness_model_map(runner: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in runner.items() if k != "models"}


def resolve_harness_config(
    config: dict[str, Any], config_path: Path, harness: str
) -> dict[str, Any]:
    """Return a normal models config for one harness.

    Routing is derived from each model's provider:
    - anthropic  -> claude harness
    - openai     -> codex harness (runner_type=codex)
    - cursor     -> cursor harness
    - ollama_cloud -> claude + codex (ollama launch <harness>)
    - opencode_id field present -> also included in opencode harness

    Example:
        ``resolve_harness_config(config, Path("config/models.json"), "codex")``
        returns ``{"runner": ..., "models": [...]}`` scoped to codex rows.
    """
    if config.get("ollama_cloud"):
        return expand_ollama_cloud_config(config, harness)
    if "runner" in config:
        return config
    runner = _load_registry_harness(config_path, harness)
    registry_models = _normalize_registry_models(config.get("models"))
    models = _registry_models_for_harness(registry_models, harness)
    return {
        "runner": _strip_harness_model_map(runner),
        "models": models,
        "_registry_models": registry_models,
    }


def resolve_build_harness_config(
    config: dict[str, Any], config_path: Path, harness: str
) -> dict[str, Any]:
    """Return runnable model rows and runner metadata for one build harness."""
    return resolve_harness_config(config, config_path, harness)


def resolve_audit_harness_config(
    config: dict[str, Any], config_path: Path, harness: str
) -> dict[str, Any]:
    """Return runnable model rows and runner metadata for one audit harness."""
    return resolve_harness_config(config, config_path, harness)


def resolve_meta_harness_config(
    config: dict[str, Any], config_path: Path, harness: str
) -> dict[str, Any]:
    """Return runnable model rows and runner metadata for one meta harness."""
    return resolve_harness_config(config, config_path, harness)


@dataclass
class BenchmarkConfig:
    """All settings needed for a benchmark run, built from CLI args and config files."""

    runner: dict[str, Any]
    config_path: Path
    results_dir: Path
    harness: str  # "opencode" | "codex" — prefix for result subdirs: results/<harness>-<slug>/
    timeout_seconds: int
    no_progress_timeout_seconds: int
    min_preview_output_tps: float | None
    min_preview_samples: int
    auto_skip_slow_preview: bool
    force: bool
    backend: LocalModelBackend | None = None
    selected_models: list[dict[str, Any]] = field(default_factory=list)
    prompt: str = ""
    followup_prompt: str | None = None
    rate_limit_policy: RateLimitWaitPolicy = field(default_factory=RateLimitWaitPolicy)


def load_opencode_config() -> dict[str, Any] | None:
    if not OPENCODE_CONFIG_PATH.exists():
        return None
    try:
        return json.loads(OPENCODE_CONFIG_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def load_opencode_ollama_api_base() -> str | None:
    payload = load_opencode_config()
    if not payload:
        return None
    base_url = (
        payload.get("provider", {}).get("ollama", {}).get("options", {}).get("baseURL")
    )
    if not isinstance(base_url, str) or not base_url:
        return None
    return base_url[:-3] if base_url.endswith("/v1") else base_url


def load_ollama_warmup_payload(path: Path) -> dict[str, Any] | None:
    payload = load_optional_json(path)
    if not payload:
        return None
    results = payload.get("results")
    if not isinstance(results, list):
        return None
    results_by_slug: dict[str, dict[str, Any]] = {}
    for entry in results:
        if not isinstance(entry, dict):
            continue
        slug = entry.get("slug")
        if isinstance(slug, str) and slug:
            results_by_slug[slug] = entry
    payload["results_by_slug"] = results_by_slug
    return payload


def existing_terminal_result(result_path: Path) -> dict[str, Any] | None:
    if not result_path.exists():
        return None
    payload = load_json(result_path)
    if payload.get("status") in TERMINAL_STATUSES:
        return payload
    return None


def mark_model_skip_by_default(config_path: Path, model_slug: str, note: str) -> bool:
    payload = load_optional_json(config_path)
    if not payload:
        return False
    models = payload.get("models")
    if not isinstance(models, list):
        return False
    changed = False
    for model in models:
        if not isinstance(model, dict):
            continue
        if model.get("slug") != model_slug:
            continue
        if model.get("skip_by_default") is not True:
            model["skip_by_default"] = True
            changed = True
        reason = model.get("selection_reason")
        note_suffix = f" {note}"
        if isinstance(reason, str) and note_suffix not in reason:
            model["selection_reason"] = reason + note_suffix
            changed = True
        break
    if not changed:
        return False
    save_json_preserve_order(config_path, payload)
    return True
