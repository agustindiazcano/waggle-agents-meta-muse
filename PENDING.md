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
| 26 | P2 | After B8: decide whether to approve FastAPI, uvicorn and the JavaScript toolchain (Node, Vite, TypeScript, three) for viewer v0 | M | pending |
| 27 | P2 | gitleaks 8.30.1 installed with winget (B0 pre-push check fails closed without it). Restart the shell so it is on PATH; the check also finds the WinGet path | M | done |
| 28 | P3 | Verify CEGIS and LLM-Modulo as prior art before ADR-023 cites them | A | pending |
| 29 | P2 | The brief refers to E9 but docs/EXPERIMENTS.md has no E9 (only E1 to E8 and the new E10). Define E9 or tell the agent to drop the reference | M | pending |
| 30 | P2 | Cloud-first testing (AGENTS.md section 3, rules 8 to 11). Decide whether the pre-push gate may rely on the cloud CI instead of a local `uv run ci` stamp (touches tools/hooks/), and ask the agent to add a workflow_dispatch workflow for the E1 dev baseline and the speed measurement | M | pending |
| 31 | P1 | STOP POINT from the brief: the measured rollout cost (10 robots, 4 humans, 45 s simulated, lidar every 4 ticks) is 22.3 s on this machine, of which about 8.7 s is the core loop and detector and about 10.5 s the lidar (2.3 ms per scan). K = 5 variants serial is about 2 minutes per validation iteration. Decide: accept, lower the lidar rate inside rollouts, cache static visibility, parallelize the K variants across processes (each is a documented deviation in ADR-025), or change the design | M | pending |
