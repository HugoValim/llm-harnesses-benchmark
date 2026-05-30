# Domain documentation layout

Tells engineering skills (`improve-codebase-architecture`, `diagnose`, `feature`, and related workflows) where to find this repo's domain language and architectural decisions.

## Layout

This repo is single-context.

- `CONTEXT.md` at the repo root is the authoritative domain glossary.
- `CONTEXT-MAP.md` does not currently exist.
- No ADR directory exists currently (`docs/adr/` is absent).

## Consumer rules

When a skill is operating in this repo:

1. Read root `CONTEXT.md` before proposing structural changes or issue decompositions.
2. Treat root `CONTEXT.md` as the shared language source for benchmark, audit, harness, result, and report terminology.
3. If an ADR directory is added later, read every `docs/adr/*.md` before proposing structural changes and respect accepted decisions.

## Authoring rules

- `CONTEXT.md` is for shared language, not implementation detail. Aliases and antonyms belong there; class names and file paths generally do not.
- ADRs, if introduced later, should use the standard four-section template: Status, Context, Decision, Consequences.
- New ADRs default to `Status: Proposed`; promotion to `Accepted` is a maintainer action.
