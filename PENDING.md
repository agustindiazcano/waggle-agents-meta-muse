# Waggle Hive: Pending

## Waiting on the maintainer
| Item | Status |
|---|---|
| Push the branches and confirm the CI workflow runs green on GitHub | pending |
| Fill API keys in `.env` (Meta, Baseten, Gemini, Modal, Meshy) and set spend caps | pending |
| Claim Meta Model API credits (deadline Nov 4, 9 PM ET), request Baseten and Modal credits, add a card | pending |
| Discord office hours: does Prompt Guard count as a Meta model for Stage One; confirm Baseten model id | pending |
| Fill judging rubric weights in `SUBMISSION.md` | pending |

## Open technical items
| Item | Note |
|---|---|
| CI workflow is untested on GitHub | Only the equivalent local commands were run. |
| `pre-commit install` not run | Hooks are configured but not installed in the local clone. |
| Compose `web` service serves a static page with `python -m http.server` | Replaced in Phase 7. |
| Hard spending cap per provider (AGENTS.md) | Variable names exist in `.env.example`; enforcement code comes with the LLM client in Phase 5. |
| Coverage is 67% | Placeholder `__main__` modules are not exercised by unit tests; verified by compose health checks instead. |
| `AGENTS.md` new version is uncommitted | It is committed unchanged in `docs/agents-rules`. The style test lands in that branch, so style rules were checked by hand on new files until then. |
