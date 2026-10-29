# Waggle Hive: Pending

Priority: P1 blocking, P2 next, P3 later, P4 backlog. Owner: M is the maintainer, A is the agent.

| # | Priority | Task | Owner | Status |
|---|---|---|---|---|
| 1 | P1 | Push `main`, then each stacked branch in the order listed in LASTCONTEXT.md with `git push -u origin <branch>`, and open each PR against the previous branch. Push after every finished branch from now on | M | pending |
| 2 | P1 | Confirm `ci.yml` runs green on GitHub | M | pending |
| 3 | P1 | Review the 11 stacked branches and merge them in order with merge commits | M | pending |
| 4 | P1 | Verify balances, expiry dates and rate limits in each provider console (Meta, Baseten, Modal, Vertex) | M | pending |
| 5 | P1 | Set provider caps in the consoles and in `.env`; rename Gemini variables to the Vertex and Modal names in `.env.example` by hand | M | pending |
| 6 | P2 | Verify Muse Glimmer availability and price per hour on Modal and Baseten (a first search found hosted endpoints elsewhere, none on those two) | M | pending |
| 7 | P2 | Verify model ids through the Meta model list (`GET /v1/models`) and fill `META_MODEL_ID`, `META_VOICE_MODEL_ID` in `.env` | M | pending |
| 8 | P2 | Read the Muse Model License text and confirm the attribution wording used in README and `web/index.html` | M | pending |
| 9 | P2 | Choose the runtime HTTP client dependency (OpenAI SDK or httpx). Check that Baseten and a Modal endpoint are OpenAI-compatible. Agent asks before adding it | M | pending |
| 10 | P2 | Verify price and latency of Muse Spark Open versus Muse Spark in the consoles, and the Baseten rate limit for 10 concurrent robots | M | pending |
| 11 | P2 | Add GitHub Actions secrets for the heavy workflow | M | pending |
| 12 | P2 | Claim Meta Model API credits (deadline Nov 4, 9 PM ET), request Baseten and Modal credits | M | pending |
| 13 | P3 | Show the "Built with Muse Spark Open" attribution card in the final video | M | pending |
| 14 | P3 | Fill judging rubric weights in `SUBMISSION.md` | M | pending |
| 15 | P3 | Remove the exit code 5 allowance in `heavy.yml` once the first heavy test exists | A | pending |
| 16 | P3 | Run `pre-commit install` in the local clone | M | pending |
| 17 | P4 | Optional: mutation testing for `waggle.control` only, if time remains | A | backlog |
| 18 | P4 | Tag demo images with the commit in the deploy script (compose uses `dev` locally) | A | backlog |
| 19 | P2 | Set branch protection on the repository by hand: require pull request review and code owner review, block force pushes. CODEOWNERS is a weak control until then | M | pending |
| 20 | P2 | Open /hooks in Claude Code to review and trust the project hooks in .claude/settings.json | M | pending |
| 21 | P1 | Phase 1 part 1: first present the plan (branches, order, risks) and wait for approval. Prompt in LASTCONTEXT.md. `docs/design-extensions` is done | A | next |
| 22 | P2 | numpy approved by the maintainer as a runtime dependency of `waggle.sim` (Phase 1 prompt). Agent adds it with uv pin, README line and this row updated when branch 1 is built | A | approved |
