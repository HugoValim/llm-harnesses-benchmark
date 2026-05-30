# Triage label vocabulary

Maps the five canonical triage roles to the actual label strings configured in this repo's issue tracker. The `triage` skill and anything that writes triage state reads this file to apply the right labels.

## Canonical roles

| Role | Meaning | Label string in this repo |
|---|---|---|
| `needs-triage` | Maintainer needs to evaluate. | `needs-triage` |
| `needs-info` | Waiting on the reporter for more information. | `needs-info` |
| `ready-for-agent` | Fully specified; an AFK agent can pick it up without context. | `ready-for-agent` |
| `ready-for-human` | Needs human implementation, judgment, external access, or design. | `ready-for-human` |
| `wontfix` | Will not be actioned. | `wontfix` |

## Category labels

| Role | Meaning | Label string in this repo |
|---|---|---|
| `bug` | Something is broken. | `bug` |
| `enhancement` | New feature or improvement. | `enhancement` |

## Override conventions

If this repo starts using different label strings, update the right-hand column to the existing strings. Do not rename labels in the issue tracker just to match the canonical names.

Every triaged issue should carry exactly one state role. Conflicting state labels should be flagged to the maintainer before any further action.
