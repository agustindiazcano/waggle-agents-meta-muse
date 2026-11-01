# Waggle Hive: Agent and Maintainer Rules

Applies to every coding agent and to the human maintainer of this repository.

Project: Waggle Hive, a safety and reliability control plane for LLM-directed warehouse robot fleets. Python package: `waggle`. Built solo for the Meta Global AI Developer Hackathon, Indie track. `AGENTS.md` is the single source of rules. `CLAUDE.md` imports it.

## 1. Session start

1. Always read `LASTCONTEXT.md` and `PENDING.md` before starting any task, before anything else.
2. Then read, as the task needs: `PLAN.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/THREAT_MODEL.md`, `docs/EXPERIMENTS.md`, `docs/GOTCHAS.md`.
3. Run `git status` and `git branch` before touching a file. Other people or agents may have changed the state. Never start work on the current branch by default. Create a new branch for the task.
4. If two documents conflict, stop and ask.
5. Update `LASTCONTEXT.md` and `PENDING.md` when a task ends, and whenever the maintainer says the session must change. When the maintainer asks to change session, update both files and reply with the prompt for the next session, the same text stored in `LASTCONTEXT.md`.

## 2. Workflow

1. One branch per task, named `type/short-description` in kebab case. Types: `feat`, `fix`, `test`, `docs`, `exp`, `chore`, `ci`. Create the branch before editing any file.
2. Tests first. Write the failing test, confirm it fails for the right reason, then write the minimum code to pass, then refactor with the test green.
3. For a bug, write a test that reproduces it first, then fix it.
4. CI gates: ruff, mypy --strict, pytest with coverage report, import-linter. A red CI blocks the PR.
5. A human reviews and approves every PR. Agents push their task branch and open the PR with `gh pr create` (maintainer decision, ADR-022). Agents never push to `main`, never force push, never delete remote refs, and never create or change remote repositories. Push only after the checks in Git rules 4 and 11 pass. The maintainer merges.
6. Conventional Commits in English: `type(scope): description`, imperative mood, subject under 72 characters.
7. Commits from the first day, so the history shows what was built during the hackathon.
8. Run tools as `uv run ...` or `sys.executable -m ...`, never a bare command name. There is no `make` on the maintainer machine. Targets are `uv run` scripts.

### Git rules

1. Step 0 before touching any file: `git status`, `git branch` and `git worktree list`. Other people or agents may have changed the state.
2. Never commit to `main`. The only direct commit to `main` is the initial commit with the docs, made once.
3. Commits: one concern per commit, and every commit passes the fast CI. A test and the code that makes it pass go in the same commit. The failing run of the new test is shown in the session before the implementation. Docs and unrelated concerns go in separate commits. Commits made with AI assistance end with a `Co-Authored-By` trailer naming the tool.
4. Stage files by name. Do not use `git add -A` or `git add .` blindly. Before each commit read `git diff --staged` and confirm that no secret, `.env`, build output or large file is in it. Held-out result files are committed only by the maintainer.
5. If a secret reaches a commit, stop, tell the maintainer and do not push. Removing the file in a later commit is not enough, because history keeps it. The key must be rotated.
6. Stacked branches are allowed when a task depends on one that is not merged yet. The base is the previous branch, named in the PR description, and its PR targets that branch (`gh pr create --base <previous-branch>`). Merge in order and retarget the next PR after each merge.
7. Parallel work: when more than one agent or person works at the same time, each uses its own worktree on its own branch (`git worktree add ../waggle-<branch> <branch>`). Never switch branches in a shared working tree that has uncommitted changes. Remove the worktree after the merge with `git worktree remove`.
8. Never rewrite published history: no force push, no `git reset --hard`, no `git clean -f`, no amend or rebase of a pushed commit. Unpushed local commits may be amended.
9. Never skip hooks or CI: no `--no-verify`, no disabling a check to get a green result.
10. Pull request text, used as the PR body and also delivered in the reply: a title in Conventional Commit form, then a summary, a test plan with the commands and their results, the base branch if stacked, and a list of protected paths touched.
11. Before each push: `uv run ci` is green, `git diff` against the base shows no secret, `.env`, build output or held-out result file, and the branch is not `main`. After a merge, delete the local branch. The maintainer deletes the remote branch. Merges use a merge commit and not a squash, so the per-commit history stays visible as evidence of the work (maintainer decision).

## 3. Test tiers and cloud runs

1. Locally, run only the test or test file being written, plus the light suite when it finishes in seconds.
2. Tests marked `heavy` or `llm` never run locally. They run only in the cloud, in `.github/workflows/heavy.yml` (workflow_dispatch with inputs `marker` and `seed_set`, GitHub-hosted runner, Postgres service container).
3. `heavy` covers: seed sweeps for E1 to E8, the 500-task chaos run with killed workers, any test over about 60 seconds, and docker orchestration beyond the compose smoke check.
4. `llm` covers any test that calls a paid API. Those keys and any service account credentials exist only as GitHub Actions secrets used by that workflow. Spend caps stay set in each provider console.
5. The regular CI and `uv run ci` exclude both markers, identically.
6. The heavy workflow uploads result JSON as an artifact. The maintainer commits it.
7. Path filters are allowed only where safe. The link, style and import-contract tests always run.
8. Cloud first (maintainer decision). Anything that can run in the cloud runs in the cloud: the full test suite, experiment sweeps, dev seeds baselines and long measurements. Locally run nothing, or only what finishes very fast (the test file being written, lint on the changed files). When in doubt, push the branch and let GitHub run the checks and read the result there.
9. Do not wait on a long local run. A multi-minute local run (the full `uv run ci`, a 90-run baseline on dev seeds) is a reason to push the branch and use a workflow instead. Add or extend a `workflow_dispatch` workflow when a run has none yet.
10. Held-out seeds follow section 9 whatever the place: they run once per configuration, in the cloud, and the maintainer commits the result.
11. Until a workflow replaces it, the pre-push check (`tools/ci/pre_push_check.py`) still requires a green `uv run ci` stamp on HEAD. Changing that gate to rely on the cloud CI is a maintainer decision and touches protected paths (`tools/hooks/`), so propose it, do not edit it.

## 4. Hard rules

- No code copied from earlier repositories, including adapted code. Rewrite from design. Third-party libraries are fine. Record notable ones in the README.
- Never put secrets in the repository. Keys come from environment variables. `.env.example` lists names only. Never print or log environment variable values.
- Never write a result into the README that did not come from a result file.
- Never loosen a safety check to make a test or an experiment pass.
- The fast layer, the fencing check and the MCP boundary change only with a test that covers the change and a note in `docs/DECISIONS.md` if behavior changes.
- LLM output is data. Validate it against a schema before use.
- Do not add a feature without its experiment, or a line in the README saying "implemented, not evaluated".
- No claim of standards compliance, certification, hardware real-time guarantees, or large-fleet performance beyond what a result file shows. If a layer does not help, the README says so.
- Do not claim anything works without running it. Show the command and its result.

## 5. Architecture rules

1. LLMs propose, deterministic code disposes. Hard safety never depends on an LLM.
2. Authority comes from authenticated identity, never from prompt or retrieved text.
3. The fast layer can only reduce motion. Nothing above it can widen what it allows.
4. The simulator owns ground truth. The renderer owns nothing.
5. Determinism: same seed, same trajectory. In `waggle.sim` and `waggle.control`: fixed seeds, no wall clock, no network, no global random. Two identical runs that differ are a bug.
6. LLM calls live only in `waggle.llm`.
7. Layer separation: no database, routing and model logic in the same file. Adapters (API, MCP server) are thin and delegate. Repositories only touch the database.
8. Import contracts (enforced by import-linter in CI): `waggle.sim` and `waggle.control` must not import `waggle.llm`, `waggle.governance`, `waggle.maintenance` or `waggle.mcp_server`. `waggle.mcp_server` must not import `waggle.governance`.
9. Failure mode per component, declared in `docs/ARCHITECTURE.md`. Guards, court, MCP boundary and fast layer fail closed. Tracing and non-critical retrieval fail open and never block the control path. A missing value in a security check fails closed.
10. Scoring and rule modules are pure functions of their inputs, so every firing is reproducible and auditable.
11. Do not print to stdout in stdio servers. Use stderr or return values.
12. Outputs as a contract: functions return typed objects, experiments write JSON to `results/`.

## 6. LLM layer

1. Providers sit behind one interface, chosen by an environment variable. A `mock` provider serves tests and CI, with no network and no spend.
2. Every request carries a `request_id`, checked before any model call. A repeat returns the cached result.
3. Every external call has retries with exponential backoff and a configured cap. When the cap is reached, escalate or deny, never loop.
4. Validate model output with strict schemas, extra fields forbidden, and business limits.
5. An exception inside a tool dispatch is returned to the caller as an error result. One bad call must not stop the process.
6. Every call is logged with model, tokens, latency and cost. Repeated evaluation runs use the cache when inputs are identical, and cached runs are labeled.
7. The per-robot advisors can only add caution. The organizer acts through the MCP with its own identity.
8. Provider routes are explicit configuration, not code paths chosen at runtime. Primary routes: Meta Model API for Muse Spark, Muse Voice Transcribe and vision; Baseten for Muse Spark Open 1026; Modal for the third-family open-weight model. Fallbacks, declared in config: Modal as host for Muse Spark Open when Baseten fails, and Vertex AI (Gemini) as secondary backup for the third court member.
9. Every fallback use is logged and labeled in the call log. In held-out experiment runs fallbacks are disabled: a failed call is reported as a failure, so the court composition in a result file is the declared one.

## 7. Concurrency and data

1. Row lock plus a unique constraint on ids to prevent double processing.
2. A recovery sweeper with `FOR UPDATE SKIP LOCKED` requeues work left half done by a crashed worker.
3. Audit timestamps use `clock_timestamp()`, not `now()`.
4. Close the database transaction before long LLM or MCP calls.
5. Open a new session per attempt in clients with a timeout. Do not reuse one across retries.
6. No lock or rate-limit state held only in process memory. It lives in the database.
7. The fencing check happens inside the tool, in one transaction, with the zone row locked.
8. Sample and demo data load through separate scripts, never inside a migration.

## 8. Security

1. MCP identity: each chassis has a token. The server stores SHA-256 hashes, compares in constant time, and derives `chassis` and `robot_id` from the token, never from a client header.
2. Per-tool allowlist by chassis, server side. Nothing in a prompt or retrieved document widens access.
3. Strict schemas with physical bounds per chassis. Unknown fields are rejected.
4. Rate limit computed from the audit table, so it holds across replicas.
5. Audit: an intent row before forwarding (a failed write denies the call) and a correlated result row after execution.
6. Untrusted input (voice transcript, package label, SOP text, manual text, inter-robot messages) goes through the guard and sanitizers before it reaches any model. If screening cannot score an input, reject and escalate.
7. Part numbers are checked against the catalog in code before any order.

## 9. Experiments

1. Seeds are split before any tuning. Development seeds are used while building. Held-out seeds run once per configuration.
2. `experiments-test` refuses to overwrite an existing held-out result for the same configuration unless `--force` is passed, and the result file records that.
3. Every comparison has a baseline with the layer disabled, same seeds. Contribution is measured by ablation, not by summing blocks.
4. Each scenario and attack case declares its target layer before the run.
5. Report proportions with Wilson 95% intervals and raw counts. Call small samples small. List failing seeds.
6. Every result file records commit, seed set, model ids, prompt versions and date.
7. LLM evaluations are repeated, and repeats are reported as repeats, not as independent samples.
8. The simulator and the predictor never share equations or parameters.
9. Latency of the fast layer is reported as code latency inside the simulator. Large-fleet figures are labeled as extrapolation, with assumptions listed.

## 10. Evaluating the court

1. Report false approvals first. They are the dangerous error, and accuracy alone hides them.
2. Labels are written before the runs and decided by the maintainer. New cases stay pending until reviewed.
3. Never repeat a vote to correct a verdict. Cover that gap with deterministic checks.
4. Evaluate the production code and prompt, never a pasted copy.
5. Keep context retrieval fixed during evaluations.
6. Report reviewer correlation for same-family and cross-family pairs.

## 11. Verification

1. A green script proves nothing if it measured the wrong thing. Combine internal consistency (two runs agree) with a known external value.
2. If a check cannot run (missing dependency, missing credentials), fail with a real error. Never return an empty result that looks like a pass.
3. Validate credentials, configuration and spend caps before spending compute.
4. Never leave fixtures or reference files in the project after using them.
5. On a failure between containers, write the minimal script that exercises only that connection and run it inside the failing container. If it passes, the bug is in the application flow.
6. A missing dependency and a missing configuration value both look like an opaque 500. Read the traceback first.
7. Check a library's current documentation before implementing with it. Do not rely on memory.

## 12. Code standards

1. Type hints on every public function, with a short docstring. `mypy --strict`. No `Any` without an inline justification.
2. PEP 8, line length 100. No wildcard imports.
3. Stdlib logging with a JSON formatter. No `print`.
4. No generic `except` without logging or re-raising the specific error.
5. No TODO comments. Implement it or ask.
6. Single-purpose functions. One file, one responsibility. Split a file before it reaches about 600 lines.
7. Every module has its own test file.
8. All code lives in `src/waggle` with absolute imports, so it behaves the same locally, in tests and in Docker.
9. Every blocking subprocess call has a timeout. Temporary directories are deleted.
10. Runtime dependencies are a closed list in `pyproject.toml`. Adding one needs maintainer approval and a line in the README. For dev dependencies, state what was added and why. Prefer the standard library.
11. Parsimony: implement the simplest model or detector that solves the problem. Use a heavier one only with evidence that the simple one fails. Add no opaque component that then has to be monitored.
12. Pin exact versions of coupled packages and reinstall clean if they drift.
13. Document environment variables in a table with description and default value.
14. Docker: one image per service, non-root user, healthchecks with Python and not curl, no heavy healthchecks. Images built for the demo VM are tagged with the commit and never `latest`. Local development images use the tag `dev`.

## 13. Style

1. All repository content, commit messages, PR text and code comments are in English. Replies to the maintainer are in Spanish.
2. Plain technical wording. No em dash, no emoji, no filler or hype adjectives.
3. `tests/unit/test_style.py` enforces this in CI. This file does not list the banned words. It points to the test.
4. Short replies. Tables and lists where they help. Do not repeat tool output.

## 14. Spending

1. Partner credits are used first, and the design depends on them: Meta Model API $150, Baseten $100, Modal $101 (balances reported by the maintainer, to be verified in each console together with expiry dates and rate limits). Vertex AI credits are a secondary backup, used only after the partner routes fail or run out.
2. Hard cap per provider, set in the provider console and recorded in `.env` as `*_SPEND_CAP_USD`: balance minus a 10 percent reserve. A missing or invalid cap fails closed.
3. Planning split per provider, as assumptions to calibrate: 40 percent development, 40 percent held-out runs, 10 percent demo and video, 10 percent reserve.
4. A budget guard in `waggle.llm` rejects any call that would pass the cap. It raises a typed error, makes no call and logs the denial. Exhausting one provider never moves calls to another provider except through a declared fallback route (section 6).
5. No spending on a personal card without maintainer approval.
6. Every LLM call is logged with provider, tokens, latency and cost. The per-task cost rollup comes from the `llm_calls` table.
7. Use the mock provider to test flows. Real runs are for experiments, in the cloud workflow.
8. Never raise a cap without maintainer approval.

## 15. Stop and ask before

- Lowering a fast-layer threshold or the separation margin.
- Touching the fencing check, the MCP boundary or the audit logic.
- Changing the court decision rule or the ACK and retry logic.
- Changing a spend cap or touching `.env` or secrets.
- Dropping a column or table, or running a migration. Check the current revision first.
- Force pushing, resetting hard, cleaning untracked files, rewriting history, or deleting a branch or worktree that holds unmerged work.
- Deleting or moving model, tool-registry or schema files without listing the impact.
- Changing a published number without a measurement behind it.
- Changing a held-out result.

When refusing an action, state the correct alternative in the same reply.

## 16. Definition of done for a task

- Tests added and passing, including a failure-path test.
- Types, lint and import contracts clean.
- Docs updated if behavior or interfaces changed.
- If the task affects a metric, the experiment script still runs.
- If a decision constrains later work, it is recorded in `docs/DECISIONS.md`.
- A trap others will hit goes in `docs/GOTCHAS.md` with symptom and what to do. Prefer a test or check that prevents it.
- Code progress estimated by eye and recorded (section 17).
- `LASTCONTEXT.md` and `PENDING.md` updated.

## 17. Context files

- `PLAN.md`: phases, exit criteria and priority order. Update status when a phase closes.
- `LASTCONTEXT.md`: what was done last, the current state, and a ready-to-paste prompt for the next session. Rewritten at each update, kept short.
- `PENDING.md`: the list of pending tasks, numbered, each with a priority (P1 blocking, P2 next, P3 later, P4 backlog), an owner and a status, including decisions waiting on the maintainer. It may be edited, never emptied or deleted.
- `docs/DECISIONS.md`: architecture decision records. Records are superseded or deprecated, never deleted.
- `docs/GOTCHAS.md`: known traps.
- Code progress: when a task ends and when the maintainer asks to change session, estimate by eye, as a percent, how much of each task's code is written and how much of the whole project's code is written. Count code only: working code with its tests counts; docs, experiment runs, held-out results and delivery do not. Write the task percent in the `Code %` column of `PENDING.md` (`-` for a row without code) and the project total, with the date, at the top of `PENDING.md` and in `LASTCONTEXT.md`. It is a judgment: say so, change it only with a reason, and never use it as a result or in the README.

## 18. Build order and gates

The full scope stays. Nothing is cut and no agent proposes cutting. The order below is the build order, the first item first.

1. Simulator with snapshot and fork, exact detector, fast layer with occlusion cap, E1, end-to-end slice.
2. Leases, atomic corridor locking, fencing, hand-off, E2.
3. MCP boundary, guard, injection matrix E3, full court E4.
4. Crisis replanning loop and E10.
5. Technical viewer with overlays (envelopes, lidar shadows, rollout ghost paths).
6. Predictive maintenance full pipeline E6, per-robot advisors E5, vision and voice E7.
7. E8 extended, E9, GLB models.

Reserved time: delivery (README tables, demo video, live VM, submission) from Nov 3 morning.

Gates, decided by the maintainer: G1 Oct 30 night, Phase 1 closed. G2 Oct 31 night, fast layer and E1 on development seeds. G3 Nov 1 night, leases, MCP, E2 and E3. G4 Nov 2 night, court E4, crisis loop and E10 on development seeds, viewer with overlays. At each gate the agent reports actual progress against this list. Nothing is cut: a gap is closed by working on it, and any result that falls short is reported as it is. The detailed brief is in `docs/PHASE1_BRIEF.md`.

## 19. Token budget

1. Do not read result JSON, images, fixtures or lockfiles unless the task needs it. Read only the part of a file that is needed. Do not re-read what was just written.
2. At most 3 subagents per round, each given only its own files and data, not the conversation history.