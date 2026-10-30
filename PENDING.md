# Waggle Hive: Pending

Priority: P1 blocking, P2 next, P3 later, P4 backlog. Owner: M is the maintainer, A is the agent.

| # | Priority | Task | Owner | Status |
|---|---|---|---|---|
| 1 | P1 | Push `main` (maintainer, once), then push each stacked branch in the order listed in LASTCONTEXT.md and open each PR against the previous branch. Agents may do the branch pushes and PRs since ADR-022; they never push `main`. Push after every finished branch from now on | M, A | pending |
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
| 21 | P1 | Superseded by row 23. Was: Phase 1 part 1 plan approval. Prompt in LASTCONTEXT.md. `docs/design-extensions` is done | A | next |
| 22 | P2 | numpy approved by the maintainer as a runtime dependency of `waggle.sim`, `waggle.control` and `waggle.validation`. Added as numpy==2.5.4 with uv and listed in the README (B3) | A | done |
| 23 | P1 | Execute `docs/PHASE1_BRIEF.md` in branch order B0 to B8 (B1 and the contract of B3 partly exist, see its status notes). Stop points: after B0 and after B8 | A | next |
| 24 | P1 | Review the hooks diff and approve the settings change after B0 (`chore/push-guard-hardening`). Restore `.claude/settings.json` by hand when required | M | pending |
| 25 | P1 | Gates G1 Oct 30 night, G2 Oct 31 night, G3 Nov 1 night, G4 Nov 2 night: read the progress report and decide what to cut from the contingency order in AGENTS.md section 18 | M | pending |
| 26 | P2 | Approved, not installed: fastapi, uvicorn[standard], and in web/ Node, Vite, TypeScript, three, @types/three, Playwright (ADR-029). Viewer v0 has its own brief for another agent | M | done |
| 27 | P2 | gitleaks 8.30.1 installed with winget (B0 pre-push check fails closed without it). Restart the shell so it is on PATH; the check also finds the WinGet path | M | done |
| 28 | P3 | Verify CEGIS and LLM-Modulo as prior art before ADR-023 cites them | A | pending |
| 29 | P2 | E9 defined as regression detection (mutation testing and planted defects) in `docs/EXPERIMENTS.md`; E10 is crisis replanning (ADR-029) | A | done |
| 30 | P2 | `uv run ci` is the fast tier (limit 3 minutes, now 1 min 46 s). Pre-push keeps the fast tier plus gitleaks; heavy tests and held-out runs go to the cloud workflow (ADR-029) | A | done |
| 31 | P1 | Decided (recommended mix): accept 5.7 s per rollout as the design basis (K = 5, H = 45 s, lidar every 4 ticks) and run K variants in the cloud for E10 and held-out runs; reduce K, H or lidar rate only in the live demo; do not vectorize walkers and driver now (about 10 percent). Recorded in ADR-025 | A | done |
| 32 | P1 | Before any paid call: finish rows 4, 5 and 12 (balances, caps in console and `.env`, claim Meta credits by Nov 4 9 PM ET), and decide row 9 (HTTP client). Then one smoke-test branch `feat/llm-provider-smoke`: mock provider plus a cloud-only `llm` test per route (Meta, Baseten, Modal), about 1 USD in total | M | pending |
| 33 | P3 | Viewer mockup (`index (1).html`, untracked in the repo root) stays as is until control, MCP, court and advisors exist. Then: state snapshot contract per tick from `waggle.sim`, branch brief, move to `web/`, remove the JavaScript mock simulation (ADR-002). Fallback for the video: viewer reads a recorded replay file, no server | M, A | backlog |
| 34 | P2 | Stale rows after PRs 16 to 22 merged: rows 1 and 3 (push and merge of the stacked branches) are done except for maintainer review of what was merged. Maintainer confirms and closes them | M | pending |
