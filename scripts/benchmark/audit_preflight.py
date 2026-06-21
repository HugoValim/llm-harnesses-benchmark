"""Deterministic D8 pre-audit scans injected into audit prompts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Compose `${SECRET_KEY:-placeholder}` / `${DJANGO_SECRET_KEY:-...}` patterns (CF#1).
_COMPOSE_SECRET_DEFAULT = re.compile(
    r"\$\{(?:DJANGO_)?SECRET_KEY\s*:-[^}]+\}",
    re.IGNORECASE,
)
# Any secret-shaped compose default expansion (CF#1 table row).
_COMPOSE_SECRET_SHAPED_DEFAULT = re.compile(
    r"\$\{(?:[A-Z0-9_]*(?:SECRET|KEY|TOKEN|PASSWORD)[A-Z0-9_]*)\s*:-[^}]+\}",
    re.IGNORECASE,
)
_DJANGO_INSECURE_LITERAL = re.compile(r"django-insecure[-\w]*", re.IGNORECASE)
_ENV_DEBUG_TRUE = re.compile(
    r"^(?:export\s+)?(?:DJANGO_)?DEBUG\s*=\s*True\b",
    re.IGNORECASE | re.MULTILINE,
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?:^|\s)(?:DJANGO_)?SECRET_KEY\s*=\s*(\S+)",
    re.IGNORECASE | re.MULTILINE,
)
_SCAN_FILENAMES = frozenset(
    {
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
        "Dockerfile",
        "README.md",
        ".env",
        ".env.example",
        ".env.local",
        ".env.sample",
    }
)
_SCAN_SUFFIXES = (".py", ".yml", ".yaml", ".env", ".example", ".md", ".txt")
_SKIP_DIRS = frozenset(
    {
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".git",
        "_runtime_verification",
        "staticfiles",
        "htmlcov",
    }
)


@dataclass(frozen=True)
class PreflightHit:
    """One deterministic secret/config pattern match."""

    path: str
    line: int
    pattern_id: str
    excerpt: str


def _iter_scan_files(project_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(project_dir.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        rel = path.relative_to(project_dir)
        if path.name in _SCAN_FILENAMES or path.name.startswith(".env"):
            files.append(path)
            continue
        if path.suffix.lower() in _SCAN_SUFFIXES and len(rel.parts) <= 6:
            files.append(path)
    return files


def _line_excerpt(line: str, *, max_len: int = 120) -> str:
    stripped = line.strip()
    if len(stripped) <= max_len:
        return stripped
    return stripped[: max_len - 3] + "..."


def _scan_file(path: Path, project_dir: Path) -> list[PreflightHit]:
    rel = path.relative_to(project_dir).as_posix()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    hits: list[PreflightHit] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if _COMPOSE_SECRET_DEFAULT.search(line):
            hits.append(
                PreflightHit(rel, line_no, "CF#1-compose-secret-default", _line_excerpt(line))
            )
        elif _COMPOSE_SECRET_SHAPED_DEFAULT.search(line):
            hits.append(
                PreflightHit(
                    rel, line_no, "CF#1-compose-shaped-default", _line_excerpt(line)
                )
            )
        if _DJANGO_INSECURE_LITERAL.search(line):
            hits.append(
                PreflightHit(rel, line_no, "CF#1-django-insecure", _line_excerpt(line))
            )
        if rel.startswith(".env") or path.name in {".env.example", ".env.sample"}:
            if _ENV_DEBUG_TRUE.search(line):
                hits.append(
                    PreflightHit(rel, line_no, "CF#10-env-debug-true", _line_excerpt(line))
                )
        match = _SECRET_ASSIGNMENT.search(line)
        if match:
            value = match.group(1).strip("'\"")
            if value and not value.startswith("${") and value not in {"''", '""'}:
                if "environ" not in line and "os.getenv" not in line:
                    hits.append(
                        PreflightHit(
                            rel, line_no, "CF#1-secret-literal", _line_excerpt(line)
                        )
                    )
    return hits


def scan_project_config_hygiene(project_dir: Path) -> list[PreflightHit]:
    """Grep project tree for D8 patterns the rubric auto-fails.

    Example:
        >>> scan_project_config_hygiene(Path("/tmp/empty-nonexistent"))
        []
    """
    root = project_dir.resolve()
    if not root.is_dir():
        return []
    hits: list[PreflightHit] = []
    seen: set[tuple[str, int, str]] = set()
    for path in _iter_scan_files(root):
        for hit in _scan_file(path, root):
            key = (hit.path, hit.line, hit.pattern_id)
            if key in seen:
                continue
            seen.add(key)
            hits.append(hit)
    return sorted(hits, key=lambda item: (item.path, item.line, item.pattern_id))


def format_audit_preflight_block(project_dir: Path) -> str:
    """Markdown block inserted into audit prompts before LLM dispatch."""
    hits = scan_project_config_hygiene(project_dir)
    lines = [
        "## Harness preflight (deterministic — mandatory input)",
        "",
        f"Project root: `{project_dir.resolve()}`",
        "",
    ]
    if not hits:
        lines.extend(
            [
                "No D8 secret/config pattern hits from harness grep.",
                "You must still manually verify D8, D9.1 probe targets, and CF#1–CF#10.",
                "",
            ]
        )
        return "\n".join(lines)
    lines.append(
        "When a row below matches, classify the cited CF type in section F unless "
        "disproved by reading the full file at that line."
    )
    lines.append("")
    lines.append("| file:line | pattern | excerpt |")
    lines.append("|---|---|---|")
    for hit in hits:
        lines.append(
            f"| `{hit.path}:{hit.line}` | {hit.pattern_id} | `{hit.excerpt}` |"
        )
    lines.append("")
    return "\n".join(lines)
