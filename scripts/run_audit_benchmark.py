#!/usr/bin/env python3
"""Deprecation shim.

The audit pipeline has been split into two scripts:

  scripts/run_audit.py         - Role 1: per-project AI audit dispatch.
                                 Replaces ``run_audit_benchmark.py --skip-meta``.
  scripts/run_meta_analysis.py - Role 2: AI meta-analysis dispatch.
                                 Replaces ``run_audit_benchmark.py --report-only``
                                 (plus auto-rebuilds comparison.md).

This file exists only to direct old invocations to the new entry points and
will be removed in a future cleanup.
"""

from __future__ import annotations

import sys

_MESSAGE = (
    "DEPRECATED: scripts/run_audit_benchmark.py has been split into two scripts.\n"
    "  Use scripts/run_audit.py for per-project AI audits (Role 1).\n"
    "  Use scripts/run_meta_analysis.py for the cross-auditor meta-analysis (Role 2).\n"
    "Role 1's --report-only rebuild writes audit-reports/<auditor>/comparison.md, including\n"
    "leader-relative normalized scores (ceiling = mean of gpt_5_5 and claude_opus_4_7 runs).\n"
    "See CLAUDE.md for the updated invocation examples.\n"
)


def main() -> int:
    sys.stderr.write(_MESSAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
