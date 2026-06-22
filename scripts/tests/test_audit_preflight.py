"""Tests for deterministic audit preflight secret/config scans."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_preflight import (
    format_audit_preflight_block,
    scan_project_config_hygiene,
)


def test_scan_finds_compose_secret_default(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "docker-compose.yml").write_text(
        "environment:\n  DJANGO_SECRET_KEY: ${DJANGO_SECRET_KEY:-django-insecure-dev}\n",
        encoding="utf-8",
    )
    hits = scan_project_config_hygiene(project)
    assert any(hit.pattern_id == "CF#1-R-compose-secret-default" for hit in hits)


def test_scan_finds_env_example_debug_true(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env.example").write_text(
        "OLLAMA_HOST=http://localhost:11434\nDJANGO_DEBUG=True\n",
        encoding="utf-8",
    )
    hits = scan_project_config_hygiene(project)
    assert any(hit.pattern_id == "CF#10-env-debug-true" for hit in hits)


def test_format_preflight_block_lists_hits(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env.example").write_text("DEBUG=True\n", encoding="utf-8")
    block = format_audit_preflight_block(project)
    assert "Harness preflight" in block
    assert "CF#10-env-debug-true" in block
    assert ".env.example:1" in block


def test_format_preflight_block_empty_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    block = format_audit_preflight_block(project)
    assert "No D8 secret/config pattern hits" in block


def test_scan_finds_readme_doc_tier_secret_literal(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text(
        "Run tests with DJANGO_SECRET_KEY=test-secret-key-for-testing pytest\n",
        encoding="utf-8",
    )
    hits = scan_project_config_hygiene(project)
    assert any(hit.pattern_id == "CF#1-D-secret-literal" for hit in hits)


def test_scan_finds_settings_runtime_tier_secret_literal(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "settings.py").write_text(
        'SECRET_KEY = "django-insecure-hardcoded"\n',
        encoding="utf-8",
    )
    hits = scan_project_config_hygiene(project)
    assert any(hit.pattern_id == "CF#1-R-secret-literal" for hit in hits)
