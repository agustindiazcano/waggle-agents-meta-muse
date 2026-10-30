"""Tables for E1 from the result files in ``results/e1/dev/`` (``uv run report``).

Every number comes from a result file. When a configuration has several files the latest by date is
used. A missing configuration is shown as missing, never as zero.
"""

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from waggle.experiments.e1_config import CONFIGS, FALSE_STOP_GAP_M

Document = Mapping[str, Any]

ABLATION_PAIRS = (
    ("any control", "no_control", "radial_lidar"),
    ("swept footprint", "radial_lidar", "envelope_lidar"),
    ("cost of real sensing", "envelope_oracle", "envelope_lidar"),
    ("beacons", "envelope_lidar", "envelope_lidar_beacons"),
    ("occlusion cap", "envelope_lidar", "envelope_occlusion_lidar"),
    ("CPA", "envelope_occlusion_lidar", "envelope_occlusion_cpa_lidar"),
)


def load_latest(results_dir: Path) -> dict[str, Document]:
    """The latest E1 development document of each configuration."""
    found: dict[str, Document] = {}
    for path in sorted((results_dir / "e1" / "dev").glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("experiment") != "e1" or document.get("seed_set") != "dev":
            continue
        name = document["configuration"]
        if name not in found or document["date"] >= found[name]["date"]:
            found[name] = document
    return found


def _pct(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def _interval(document: Document, key: str) -> str:
    p = document["proportions"][key]
    return (
        f"{p['runs_with']}/{p['runs']} ({_pct(p['runs_with'] / p['runs'])}, "
        f"{_pct(p['wilson95_low'])} to {_pct(p['wilson95_high'])})"
    )


def _row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    return [_row(header), _row(["---"] * len(header)), *(_row(r) for r in rows), ""]


def _safety(docs: Mapping[str, Document]) -> list[str]:
    header = [
        "Configuration",
        "Runs with a human collision (Wilson 95%)",
        "Human collisions",
        "Robot collisions",
        "Separation violations",
        "Near misses",
        "Human collisions without unavoidable cases",
    ]
    rows = []
    for config in CONFIGS:
        d = docs.get(config.name)
        if d is None:
            rows.append([f"`{config.name}`", "missing", "", "", "", "", ""])
            continue
        c, x = d["counts"], d["counts_excluding_unavoidable"]
        rows.append(
            [
                f"`{config.name}`",
                _interval(d, "human_collision"),
                str(c["human_collisions"]),
                str(c["robot_collisions"]),
                str(c["separation_violations"]),
                str(c["near_misses"]),
                str(x["human_collisions"]),
            ]
        )
    return ["## Safety", "", *_table(header, rows)]


def _ratio(docs: Mapping[str, Document], name: str) -> float | None:
    """Tasks of a configuration over tasks of no_control on the same runs."""
    base, doc = docs.get("no_control"), docs.get(name)
    if base is None or doc is None:
        return None
    shared = {(r["scenario"], r["seed"]) for r in base["runs"]} & {
        (r["scenario"], r["seed"]) for r in doc["runs"]
    }
    base_tasks = sum(
        r["tasks_completed"] for r in base["runs"] if (r["scenario"], r["seed"]) in shared
    )
    doc_tasks = sum(
        r["tasks_completed"] for r in doc["runs"] if (r["scenario"], r["seed"]) in shared
    )
    return None if base_tasks == 0 else float(doc_tasks) / float(base_tasks)


def _cost(docs: Mapping[str, Document]) -> list[str]:
    header = [
        "Configuration",
        "Stop episodes",
        "False stops",
        "Tasks",
        "Throughput vs no_control",
        "Median latency (us)",
        "Worst run p99 (us)",
    ]
    rows = []
    for config in CONFIGS:
        d = docs.get(config.name)
        if d is None:
            rows.append([f"`{config.name}`", "missing", "", "", "", "", ""])
            continue
        ratio = _ratio(docs, config.name)
        latency = d["latency"]
        rows.append(
            [
                f"`{config.name}`",
                str(d["stops"]["episodes"]),
                str(d["stops"]["false_stops"]),
                str(d["tasks_completed"]),
                "n/a" if ratio is None else f"{ratio:.2f}",
                f"{latency['median_of_run_medians_us']:.0f}" if latency["calls"] else "n/a",
                f"{latency['max_of_run_p99_us']:.0f}" if latency["calls"] else "n/a",
            ]
        )
    return ["## Cost", "", *_table(header, rows)]


def _delta(a: Document, b: Document, key: str) -> str:
    return f"{b['counts'][key] - a['counts'][key]:+d}"


def _ablation(docs: Mapping[str, Document]) -> list[str]:
    header = [
        "Block",
        "From",
        "To",
        "Human collisions",
        "Separation violations",
        "Stop episodes",
    ]
    rows = []
    for label, left, right in ABLATION_PAIRS:
        a, b = docs.get(left), docs.get(right)
        if a is None or b is None:
            rows.append([label, f"`{left}`", f"`{right}`", "missing", "", ""])
            continue
        stops = b["stops"]["episodes"] - a["stops"]["episodes"]
        rows.append(
            [
                label,
                f"`{left}`",
                f"`{right}`",
                _delta(a, b, "human_collisions"),
                _delta(a, b, "separation_violations"),
                f"{stops:+d}",
            ]
        )
    return [
        "## Ablation pairs (change from the first to the second, same seeds)",
        "",
        *_table(header, rows),
        "Envelope with CPA but without the occlusion cap is not run.",
        "",
    ]


def _failing(docs: Mapping[str, Document]) -> list[str]:
    lines = ["## Failing seeds", ""]
    for config in CONFIGS:
        d = docs.get(config.name)
        if d is None:
            continue
        seeds = ", ".join(f"{f['scenario']}/{f['seed']}" for f in d["failing_seeds"]) or "none"
        lines += [f"- `{config.name}` ({len(d['failing_seeds'])}): {seeds}"]
    base = docs.get("no_control")
    if base is not None:
        cases = ", ".join(f"{u['scenario']}/{u['seed']}" for u in base["unavoidable_cases"])
        lines += ["", f"Unavoidable cases ({len(base['unavoidable_cases'])}): {cases or 'none'}"]
    return [*lines, ""]


def _provenance(docs: Mapping[str, Document]) -> list[str]:
    rows = [
        [f"`{c.name}`", d["commit"][:10], d["date"], d["platform"]]
        for c in CONFIGS
        if (d := docs.get(c.name)) is not None
    ]
    return ["## Provenance", "", *_table(["Configuration", "Commit", "Date", "Platform"], rows)]


def render(docs: Mapping[str, Document]) -> str:
    """The report as Markdown."""
    runs = sorted({len(d["runs"]) for d in docs.values()})
    lines = [
        "# E1 development results",
        "",
        "Development seeds only. Held-out seeds were not run. Every control value is an "
        "assumption that is not calibrated. Samples are small: "
        f"{', '.join(map(str, runs)) or 'no'} runs per configuration. Runs with a human "
        "collision are counted per run, and the counts of episodes are not independent samples. "
        f"A false stop is a stop that starts with every human farther than {FALSE_STOP_GAP_M} m, "
        "so in a scenario without humans every stop is a false stop, whatever stopped the robot. "
        "Latency is the code latency of `control_step` on the platform listed below, not a "
        "real-time bound.",
        "",
        *_safety(docs),
        *_cost(docs),
        *_ablation(docs),
        *_failing(docs),
        *_provenance(docs),
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Write ``results/e1/dev/report.md`` from the result files. Fails when there are none."""
    args = list(sys.argv[1:] if argv is None else argv)
    results_dir = Path(args[0]) if args else Path("results")
    docs = load_latest(results_dir)
    if not docs:
        print(f"report: no E1 result files under {results_dir / 'e1' / 'dev'}", file=sys.stderr)
        return 1
    path = results_dir / "e1" / "dev" / "report.md"
    path.write_text(render(docs), encoding="utf-8")
    print(f"report: wrote {path} ({len(docs)} configurations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
