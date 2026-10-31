# Waggle Hive: E3 development corpus

`cases.json` contains 25 synthetic development declarations, not results. No case has been evaluated. All reviews are pending and all labels, reviewers and rationales are null. The maintainer decides labels before any evaluation (AGENTS.md sections 9 and 10).

| Threat | Cases | Declared target layers |
|---|---|---|
| T1 | E3-T1-01 to 03 | MCP identity |
| T2 | E3-T2-01 to 03 | MCP schema bounds, fast layer |
| T3 | E3-T3-01 to 03 | Catalog check |
| T4 | E3-T4-01 to 03 | Read-back and item resolution |
| T5 | E3-T5-01 to 03 | Message schema, MCP identity |
| T6 | E3-T6-01 to 03 | Court unanimity |
| T11 | E3-T11-01 to 03 | Output schema |
| T18 | E3-T18-01 to 04 | Untrusted-data boundary, plan schema, plan validator |

Each case records its id, threat, target layer, source, entry point, synthetic setup, exact input, probe description, construction and review metadata. `directive`, `reference` and `malformed_output` describe how the text was constructed. They are not ground-truth labels and must not be used to score the guard. Reference cases include near-lookalikes intended for false-rejection measurement after review. T11 references concern output structure, not the truth of a classifier's verdict on an underlying input.

Review procedure:

1. Inspect the input and setup together. The setup is a trusted fixture declaration; the input is untrusted data. Synthetic part numbers, identities and limits are not production configuration.
2. The maintainer chooses `benign`, `injection` or `uncertain`, records their identity and a nonempty rationale, then changes status to `reviewed`. Pending cases retain null label, reviewer and rationale. Keep ids stable; record revisions in Git before a run.
3. Run `uv run pytest tests/unit/experiments/test_e3_corpus.py -q`. This checks declarations, coverage and review metadata without evaluating any classifier. It accepts complete reviewed metadata and does not force reviewed cases back to pending.
4. A future evaluator must refuse pending cases before any model call. It must map each setup and entry point to an explicit typed fixture and fail with a real error when a required layer is missing. Do not count an unimplemented layer as a successful rejection, or silently omit cases.

No evaluation runner is added by this corpus. The eventual run uses the production implementations, the same reviewed development cases for all ablations, fixed retrieval, and recorded commit, corpus version/hash, model ids, prompt versions and date. Store measured results under `results/e3/dev/`; preserve raw per-case outcomes, misses and false rejections. Report repeats as repeats, not independent cases. This small corpus is not a held-out set or evidence of attack coverage beyond the listed probes.

Integration gaps made explicit by the declarations:

- `model_output` cases enter response validation directly. Do not sanitize malformed JSON before checking it.
- `incident_text` is a threat-model source, but is not an `UntrustedSource` member yet. It needs an explicit sanitizer/guard integration before evaluation, with tests. Do not silently treat an incident report as trusted context.
- Message schema, item read-back, catalog compatibility, production court prompts, planner schema and planner validation still need their production integration. The pure court decision rule is not a substitute for testing the production prompt.
- A catalog existence check alone may accept E3-T3-02's incompatible but existing part. Measure and report that gap; do not claim existence establishes compatibility.
