"""Tests for D9 production-hardening preflight."""

from __future__ import annotations

from pathlib import Path

from benchmark.d9_preflight import scan_d9_preflight, write_d9_preflight


def _write_minimal_project(
    project_dir: Path,
    *,
    healthcheck: bool = False,
    logging: bool = False,
    restart: bool = False,
    user: bool = False,
    sigterm: bool = False,
) -> None:
    project_dir.mkdir(parents=True)
    docker_lines = ["FROM python:3.13.13-slim", "WORKDIR /app"]
    if user:
        docker_lines.extend(
            [
                "RUN useradd appuser",
                "USER appuser",
            ]
        )
    if healthcheck:
        docker_lines.append(
            "HEALTHCHECK CMD curl -f http://127.0.0.1:8000/health/ || exit 1"
        )
    (project_dir / "Dockerfile").write_text("\n".join(docker_lines) + "\n")

    compose_lines = ["services:", "  web:", "    image: app"]
    if restart:
        compose_lines.append("    restart: unless-stopped")
    if healthcheck:
        compose_lines.extend(
            [
                "    healthcheck:",
                "      test: ['CMD', 'curl', '-f', 'http://localhost:8000/health/']",
            ]
        )
    (project_dir / "docker-compose.yml").write_text("\n".join(compose_lines) + "\n")

    settings = "DEBUG = False\n"
    if logging:
        settings += "LOGGING = {'version': 1, 'handlers': {}}\n"
    (project_dir / "settings.py").write_text(settings)

    consumer = "from channels.generic.websocket import AsyncWebsocketConsumer\n"
    if sigterm:
        consumer += """
import asyncio

class ChatConsumer(AsyncWebsocketConsumer):
    async def stream(self):
        try:
            async for chunk in self.llm.astream([]):
                await self.send_json({"t": chunk})
        except asyncio.CancelledError:
            raise
"""
    else:
        consumer += "\nclass ChatConsumer(AsyncWebsocketConsumer):\n    pass\n"
    (project_dir / "chat" / "consumers.py").parent.mkdir(parents=True, exist_ok=True)
    (project_dir / "chat" / "consumers.py").write_text(consumer)


def test_scan_d9_preflight_all_pass(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_minimal_project(
        project,
        healthcheck=True,
        logging=True,
        restart=True,
        user=True,
        sigterm=True,
    )
    result = scan_d9_preflight(project)
    assert result["passed_count"] == 5
    assert result["checks"]["healthcheck"]["pass"] is True
    assert result["checks"]["sigterm_shutdown"]["pass"] is True


def test_scan_d9_preflight_none_pass(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_minimal_project(project)
    result = scan_d9_preflight(project)
    assert result["passed_count"] == 0


def test_write_d9_preflight(tmp_path: Path) -> None:
    result_dir = tmp_path / "codex-demo"
    project = result_dir / "project"
    _write_minimal_project(project, logging=True, restart=True)
    path = write_d9_preflight(result_dir, project)
    assert path is not None
    assert path.name == "d9-preflight.json"
    assert path.is_file()


def test_build_d9_subcheck_cohort_section(tmp_path: Path) -> None:
    from benchmark.d9_preflight import build_d9_subcheck_cohort_section

    projects_root = tmp_path / "projects"
    for name, flags in (
        ("codex-a", {"logging": True}),
        ("opencode-b", {"restart": True, "user": True}),
    ):
        _write_minimal_project(projects_root / name / "project", **flags)

    section = build_d9_subcheck_cohort_section(benchmark_projects_root=projects_root)
    assert "D9 sub-check cohort" in section
    assert "D9.2 logging" in section
    assert "Pass | Total | Rate" in section
