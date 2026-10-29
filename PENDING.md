# Waggle Hive: Pending

Priority: P1 blocking, P2 next, P3 later, P4 backlog. Owner: M is the maintainer, A is the agent.

| # | Priority | Task | Owner | Status |
|---|---|---|---|---|
| 1 | P1 | Push the stacked branches in order and open each PR against the previous branch | M | pending |
| 2 | P1 | Confirm `ci.yml` runs green on GitHub | M | pending |
| 3 | P1 | Branch `docs/providers-and-credits`: ADR-015, ADR-016, budget guard, role routing | A | next |
| 4 | P1 | Branch `chore/hooks-and-owners`, then `chore/final-check` | A | queued |
| 5 | P2 | Verify balances, expiry dates and rate limits in each provider console, including Vertex | M | pending |
| 6 | P2 | Choose the Modal third-family model | M | pending |
| 7 | P2 | Set provider caps in the consoles and in `.env`; rename Gemini variables to Vertex in `.env` by hand | M | pending |
| 8 | P2 | Add GitHub Actions secrets for the heavy workflow | M | pending |
| 9 | P2 | Claim Meta Model API credits (deadline Nov 4, 9 PM ET), request Baseten and Modal credits | M | pending |
| 10 | P3 | Office hours: does Prompt Guard count as a Meta model for Stage One | M | pending |
| 11 | P3 | Fill judging rubric weights in `SUBMISSION.md` | M | pending |
| 12 | P3 | Remove the exit code 5 allowance in `heavy.yml` once the first heavy test exists | A | pending |
| 13 | P3 | Run `pre-commit install` in the local clone | M | pending |
| 14 | P4 | Optional: mutation testing for `waggle.control` only, if time remains | A | backlog |
| 15 | P4 | Tag demo images with the commit in the deploy script (compose uses `dev` locally) | A | backlog |