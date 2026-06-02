# Troubleshooting

## `python: command not found`

This repo documents commands with `python3`. If local tooling expects `python`,
create a local alias or virtual environment where `python` points to Python
3.10+.

Verify:

```bash
python3 --version
```

## Missing Agent CLI

Benchmark harnesses shell out to external CLIs:

- opencode: `opencode`
- Codex: `codex`
- Claude Code: `claude`
- Cursor CLI: `agent`

Verify the selected CLI is on `PATH`:

```bash
command -v opencode
command -v codex
command -v claude
command -v agent
```

## Auth Failures

Auth depends on the selected provider and harness.

- OpenRouter-backed opencode rows need `OPENROUTER_API_KEY` or a working
  opencode provider config.
- Codex subscription rows need `codex login` in `~/.codex` or `OPENAI_API_KEY` in
  the environment.
- Claude subscription rows need `claude login` in `~/.claude`.
- Cursor subscription rows need `agent login` in `~/.config/cursor` or
  `CURSOR_API_KEY` in the environment.
- Ollama Cloud rows route through `ollama launch`; verify `ollama` auth and model
  access outside the benchmark first. For Codex + `ollama launch codex`, remove
  legacy `[profiles.ollama-launch]` from `~/.codex/config.toml` if Codex 0.134+
  rejects the profile (keep `ollama-launch.config.toml` overlay).

Never paste API keys into config files, prompts, generated projects, or logs.

## Runtime Verification Cannot Reach Ollama

The generated app brief expects a local or reachable Ollama server.

Check:

```bash
ollama list
ollama pull qwen2.5:7b
```

Set these only when defaults are wrong:

```bash
export OLLAMA_HOST=http://localhost:11434
export OLLAMA_MODEL=qwen2.5:7b
```

## Docker disk usage

Phase 2 of `run_benchmark.py` has each agent run `docker build` and
`docker compose up --build`. A full model batch can leave tens of gigabytes of
build cache and unused images on the host.

By default, when a benchmark batch finishes, the harness
runs:

```bash
docker builder prune -a -f
docker system prune -a -f
```

These commands remove **all** unused Docker build cache and images on the
machine, not only benchmark-tagged artifacts. To keep existing unused images,
pass `--no-docker-prune` on `run_benchmark.py`.

## Docker Failures

Runtime verification builds and runs untrusted generated projects in Docker.
Failures usually come from generated Dockerfiles, missing dependencies, or a
Compose service that does not publish a usable port.

Start with one target:

```bash
python3 scripts/analyze_results_runtime.py --only <harness>-<slug>
```

Then inspect:

```text
results/<harness>-<slug>/project/_runtime_verification/
```

## Slow Or Stalled Runs

Use a smaller selection first:

```bash
python3 scripts/run_benchmark.py --harness opencode --model <slug> --jobs 1
```

Useful controls:

- `--timeout-minutes`: total timeout per run.
- `--no-progress-minutes`: fail when stdout, stderr, and project files are idle.
- `--max-runs`: cap selected benchmark runs.

## Stale opencode Lock

Stale `run_benchmark.py` or `opencode` processes can hold the opencode SQLite
database lock at `~/.local/share/opencode/opencode.db`. The runner attempts to
handle stale opencode processes before each run. If a run hangs before writing
events, check for leftover local processes before retrying.
