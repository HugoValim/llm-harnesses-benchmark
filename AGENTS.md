# Repository Guidelines

## Project Structure & Module Organization

This repository is a Python benchmark harness for generating and auditing Django + Channels chat app implementations. Core harness code lives in `scripts/benchmark/`, with executable entrypoints in `scripts/` such as `scripts/run_benchmark.py`, `scripts/run_audit.py`, and `scripts/analyze_results_runtime.py`. Tests live in `scripts/tests/`.

Configuration files are in `config/`; prompts used by benchmark and audit runs are in `prompts/`; generated aggregate reports are in `docs/`. Runtime outputs are written under `results/` and `audit-reports/` and should not be treated as source files.

## Build, Test, and Development Commands

- `pytest scripts/tests` runs the local regression suite.
- `python scripts/run_benchmark.py --harness opencode --report-only` rebuilds the opencode aggregate report without launching agents.
- `python scripts/run_benchmark.py --harness claude --report-only` rebuilds the Claude Code aggregate report.
- `python scripts/run_audit.py --report-only` rebuilds audit comparison output.
- `python scripts/analyze_results_runtime.py --only <result-dir>` validates one generated project through Django, browser, and Docker checks.

Full benchmark runs can be expensive and depend on external CLIs and credentials. Prefer single-model or report-only commands while developing harness changes.

## Coding Style & Naming Conventions

Use Python 3.10+ syntax and explicit types for new functions. Keep functions focused and short, prefer early returns over nested conditionals, and include offending values in exception messages. Use specific benchmark-domain names, for example `result_dir`, `harness_slug`, or `audit_report_path`.

Follow existing boundaries: process execution belongs in runner modules, config parsing in `scripts/benchmark/config.py`, and report formatting in report modules. Do not hardcode secrets; read them from environment or existing tool config.

## Testing Guidelines

Use `pytest` for all tests. Add tests under `scripts/tests/test_*.py`, matching the behavior under change. Bug fixes need regression tests. Mock external process and filesystem effects with named fakes or temp paths; do not call real agent CLIs in unit tests.

## Commit & Pull Request Guidelines

Git history uses Conventional Commit style, for example `fix(benchmark): guard agent workspaces before launch` and `test(benchmark): cover qwen opencode workspace escape`. Keep commits atomic by concern.

Pull requests should describe changed harness behavior, list verification commands, and call out new config, prompt, or external CLI assumptions. Link issues when relevant and include report diffs when generated docs change.

## Security & Configuration Tips

Never commit API keys, generated home configs, or benchmark credentials. Treat `config/opencode.benchmark.json` as generated. Be careful with `results/<harness>-<slug>/project` contents: they are model-generated projects and may contain unsafe commands or dependency choices.
