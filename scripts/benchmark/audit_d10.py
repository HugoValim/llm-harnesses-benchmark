"""Deterministic D10 (code quality) scoring from static-analysis probe output.

The harness computes D10 before LLM audit dispatch and reconciles the
auditor's section-B score afterward so inflated D10 cannot pass unchecked.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from benchmark.audit_report import parse_report_scores
from benchmark.util import save_json

D10_MAX = 10
D10_UNVERIFIED_DEFAULT = 3

_BARE_EXCEPT_RE = re.compile(
    r"^\s*except\s*(Exception\s*)?\s*:\s*$",
    re.MULTILINE,
)
_DIM10_ROW_RE = re.compile(
    r"^\|\s*\**\s*D?10\s*\**\s*"
    r"\|\s*.+?\|\s*\**\s*(\d+)\s*/\s*(\d+)\s*\**\s*\|",
    re.MULTILINE | re.IGNORECASE,
)
_SECTION_C_TOTAL_RE = re.compile(
    r"(Total(?:\s+score)?\s*[:\n/—-]+\s*\*{0,2}\s*)(\d+)(\s*/\s*100\s*\*{0,2})",
    re.IGNORECASE,
)


@dataclass
class D10Result:
    score: int
    max_score: int = D10_MAX
    reasons: list[str] = field(default_factory=list)
    cf13: bool = False
    verified: bool = True
    unverified_reason: str | None = None


def load_static_analysis(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def count_bare_excepts(project_dir: Path) -> int:
    """Count bare ``except:`` / ``except Exception:`` in application source."""
    if not project_dir.is_dir():
        return 0
    total = 0
    for path in project_dir.rglob("*.py"):
        rel_parts = path.relative_to(project_dir).parts
        if any(
            part in {".git", "node_modules", "__pycache__", "migrations"}
            or part.startswith(".venv")
            or part in ("venv", "env", "site-packages")
            for part in rel_parts
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        total += len(_BARE_EXCEPT_RE.findall(text))
    return total


def compute_d10_from_probe(
    payload: dict[str, Any] | None,
    *,
    project_dir: Path | None = None,
) -> D10Result:
    """Apply audit-v3.6 D10 triggers mechanically from probe JSON."""
    if payload is None or payload.get("status") == "error":
        reason = "probe missing or failed"
        if payload and payload.get("error"):
            reason = str(payload["error"])
        return D10Result(
            score=D10_UNVERIFIED_DEFAULT,
            reasons=[f"D10 unverified — {reason}"],
            verified=False,
            unverified_reason=reason,
        )

    score = D10_MAX
    reasons: list[str] = []
    loc = max(int(payload.get("lines_of_code") or 0), 1)
    ruff = payload.get("ruff") or {}
    mypy = payload.get("mypy") or {}
    bandit = payload.get("bandit") or {}
    radon_cc = payload.get("radon_cc") or {}
    radon_mi = payload.get("radon_mi") or {}

    ruff_errors = int(ruff.get("total_errors") or 0)
    mypy_errors = int(mypy.get("total_errors") or 0)
    bandit_high = int(bandit.get("high") or 0)
    bandit_medium = int(bandit.get("medium") or 0)
    mi_below = int(radon_mi.get("modules_below_65") or 0)

    per_kloc = ruff_errors / (loc / 1000)
    if per_kloc > 5:
        score -= 2
        reasons.append(
            f"ruff.total_errors={ruff_errors} ({per_kloc:.1f}/kLOC > 5): -2"
        )

    if mypy_errors > 10:
        score -= 2
        reasons.append(f"mypy.total_errors={mypy_errors} > 10: -2")

    high_complexity = [
        o
        for o in (radon_cc.get("top_offenders") or [])
        if int(o.get("complexity") or 0) >= 20
    ]
    if high_complexity:
        score -= 2
        sample = high_complexity[0]
        reasons.append(
            f"radon_cc complexity>={sample.get('complexity')} "
            f"({sample.get('file')}:{sample.get('function')}): -2"
        )

    if mi_below > 0:
        score -= 1
        offenders = radon_mi.get("top_offenders") or []
        lowest = offenders[0]["file"] if offenders else "unknown"
        reasons.append(f"radon_mi.modules_below_65={mi_below} ({lowest}): -1")

    if bandit_high > 0:
        score -= 2
        reasons.append(f"bandit.high={bandit_high} (application scope): -2")

    if bandit_medium > 2:
        score -= 1
        reasons.append(f"bandit.medium={bandit_medium} > 2: -1")

    bare_excepts = count_bare_excepts(project_dir) if project_dir else 0
    if bare_excepts > 2:
        score -= 1
        reasons.append(f"bare except count={bare_excepts} > 2: -1")

    cf13 = (
        ruff_errors > 50
        or mypy_errors > 50
        or bandit_high > 0
        or any(
            int(o.get("complexity") or 0) >= 30
            for o in (radon_cc.get("top_offenders") or [])
        )
    )
    if cf13:
        score = 0
        reasons.append("CF#13 catastrophic code quality — D10 capped at 0")

    score = max(0, min(D10_MAX, score))
    if not reasons:
        reasons.append(
            "clean application-scope static analysis "
            f"(ruff={ruff_errors}, mypy={mypy_errors}, bandit.high={bandit_high})"
        )
    return D10Result(score=score, reasons=reasons, cf13=cf13, verified=True)


def format_d10_precomputed_block(result: D10Result) -> str:
    """Prompt block the LLM auditor must copy into section B for D10."""
    status = "verified" if result.verified else "unverified"
    lines = [
        f"Precomputed D10 ({status}): {result.score}/{result.max_score}",
        "Mandatory — copy this score into section B row 10; do not override upward.",
    ]
    for reason in result.reasons:
        lines.append(f"- {reason}")
    if result.cf13:
        lines.append("- Section F MUST list CF#13 when this block shows CF#13.")
    return "\n".join(lines)


def parse_report_d10_score(report_text: str) -> int | None:
    parsed = parse_report_scores(report_text)
    return parsed.dim_score(10)


def reconcile_report_d10(
    report_path: Path,
    computed: D10Result,
    *,
    reconciliation_path: Path,
) -> dict[str, Any]:
    """Compare auditor D10 to harness computation; patch report if inflated."""
    report_text = report_path.read_text(encoding="utf-8")
    auditor_d10 = parse_report_d10_score(report_text)
    delta = 0
    patched = False
    new_text = report_text

    if auditor_d10 is None:
        action = "auditor_missing_d10"
    elif auditor_d10 > computed.score:
        delta = auditor_d10 - computed.score
        new_text = _patch_d10_row(report_text, computed.score)
        new_text = _patch_total_score(new_text, delta)
        report_path.write_text(new_text, encoding="utf-8")
        patched = True
        action = "patched_downward"
    elif auditor_d10 < computed.score:
        action = "auditor_stricter"
        delta = computed.score - auditor_d10
    else:
        action = "match"

    payload = {
        "computed_d10": computed.score,
        "auditor_d10": auditor_d10,
        "delta": delta,
        "action": action,
        "patched": patched,
        "cf13": computed.cf13,
        "verified": computed.verified,
        "reasons": computed.reasons,
    }
    save_json(reconciliation_path, payload)
    return payload


def _patch_d10_row(report_text: str, score: int) -> str:
    def repl(match: re.Match[str]) -> str:
        max_score = match.group(2)
        label = match.group(0).split("|")[2].strip() if "|" in match.group(0) else "Code quality (tool-backed)"
        return (
            f"| 10 | {label} | {score} / {max_score} | "
            f"harness-adjusted D10 (auditor score exceeded precomputed value) |"
        )

    updated, count = _DIM10_ROW_RE.subn(repl, report_text, count=1)
    if count:
        return updated
    return report_text


def _patch_total_score(report_text: str, subtract: int) -> str:
    if subtract <= 0:
        return report_text

    def repl(match: re.Match[str]) -> str:
        old = int(match.group(2))
        new_score = max(0, old - subtract)
        return f"{match.group(1)}{new_score}{match.group(3)}"

    updated, count = _SECTION_C_TOTAL_RE.subn(repl, report_text, count=1)
    if count:
        return updated

    # Fallback: first **NN / 100** after section C heading
    section_c = re.search(
        r"(?:^|\n)(?:##\s+)?C\.\s+\*{0,2}Total[^\n]*\n+(?:\*{0,2}\s*)(\d+)(\s*/\s*100\s*\*{0,2})",
        report_text,
        re.IGNORECASE,
    )
    if not section_c:
        return report_text
    old = int(section_c.group(1))
    new_score = max(0, old - subtract)
    start, end = section_c.span(1)
    return report_text[:start] + str(new_score) + report_text[end:]
