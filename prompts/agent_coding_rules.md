Prompt-Version: agent-coding-rules-v1.0

## Operating mode (AI-driver directives)

- Explore -> plan -> execute for any non-trivial change. Skip planning only
  for changes that are trivial and reversible.
- When ambiguous, stop and ask for focused clarifying questions rather than
  guessing.
- Push back on unsafe, ambiguous, or technical-debt-heavy requests; propose
  a safer alternative instead of silently complying.
- Do not flatter, agree reflexively, or pad responses with filler.

## Safety guardrails

- Never hardcode secrets (tokens, API keys, passwords, connection strings).
  Use environment variables or files excluded from version control.
- Validate and sanitize all external inputs before using them.
- Prefer least-privileged tools and credentials; never request elevated
  permissions you do not need for the task.
- Never run destructive operations without explicit user approval. Examples:
  recursive deletes, force pushes, history rewrites, hook bypass flags,
  global config changes, schema migrations on shared data, mass renames.
- Do not commit, push, open PRs, or merge unless the user asks. Never skip
  pre-commit hooks. Never rewrite history that has been pushed.
- If a request would expose secrets, weaken security posture, or break a
  reproducible build, refuse and explain.

## Code style

- Functions: 4–20 lines. Split if longer.
- Files: under 500 lines. Split by responsibility.
- One thing per function; one responsibility per module (SRP).
- Names: specific and unique. Avoid `data`, `handler`, `Manager`. Prefer names
  that return fewer than five `grep` hits in the codebase.
- Types: explicit. No `any`, no `Dict`, no untyped functions.
- No code duplication. Extract shared logic into a function or module.
- Early returns over nested ifs. Max two indentation levels deep.
- Exception messages must include the offending value and expected shape.
- Prefer immutable data and pure functions when practical.
- Keep diffs minimal and atomic per concern.

## Comments

- Keep your own comments. Don't strip them on refactor — they carry intent and
  provenance.
- Write WHY, not WHAT. Skip `// increment counter` above `i++`.
- Docstrings on public functions: intent + one usage example.
- Reference issue numbers / commit SHAs when a line exists because of a specific
  bug or upstream constraint.

## Tests

- Run tests with a single command: `<project-specific>`.
- Every new function gets a test. Bug fixes get a regression test.
- Mock external I/O (API, DB, filesystem) with named fake classes, not inline
  stubs.
- Tests must be F.I.R.S.T: fast, independent, repeatable, self-validating,
  timely.

## Dependencies & environment

- Inject dependencies through constructor or parameter, not global/import wiring.
- Wrap third-party libraries behind a thin interface owned by this project.
- Follow the framework's convention (Python, CPP, etc.).
- Prefer small focused modules over god files.
- Predictable paths: controller/model/view, `src/lib/test`, etc.
- Use the project's declared environment and package manager; do not install
  packages globally or into a different environment.
- Follow the project's dependency-pinning style (lockfile, exact pins, or
  ranges); justify any new dependency.
- Use the language default formatter (`black`, `cargo fmt`, etc.). Don't discuss style beyond that.
- Structured JSON when logging for debugging or observability.
- Plain text only for user-facing CLI output.

## Verification gate

"Done" only if you report at least one of: a passing automated test; clean
lint, type-check, or build on touched code; or a concrete command whose output
matches expectation. "Looks right" alone does not count.
