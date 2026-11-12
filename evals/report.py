"""
report.py - turn every results file into one Markdown scoreboard: evals/report.md

You paste this scoreboard into the README. The web app's Evaluation tab shows the same numbers.
"""
import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"
REPORT = Path(__file__).resolve().parent / "report.md"


def percent(value):
    if value is None:
        return "n/a"
    return f"{value * 100:.0f}%"


def load_results():
    runs = []
    benchmark = None
    if RESULTS.exists():
        for path in sorted(RESULTS.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if path.name == "benchmark.json":
                benchmark = data
            else:
                runs.append(data)
    return runs, benchmark


def write_report():
    runs, benchmark = load_results()
    lines = ["# Countersign evaluation", ""]

    if runs:
        lines.append("## Scoreboard")
        lines.append("")
        lines.append("| Configuration | Split | Offers x repeats | Accuracy | Traps approved | Good offers blocked | Field accuracy | Fallback rate | Median s | Slowest 5% s | AI calls / offer | Cost / offer |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for run in runs:
            s = run["summary"]
            lines.append(
                f"| {run['config']} | {run['split']} | {s['offers']} x {run['repeats']} | {percent(s['accuracy'])} "
                f"| {len(s['falseApprovals'])} | {len(s['falseRejections'])} | {percent(s['fieldAccuracy'])} "
                f"| {percent(s['fallbackRate'])} | {s['medianSeconds']:.2f} | {s['p95Seconds']:.2f} "
                f"| {s['avgAiCalls']:.1f} | ${s['avgCost']:.4f} |"
            )
        lines.append("")
        lines.append("Bar to ship: 0 traps approved on the test split, 2 or fewer good offers blocked, field accuracy of 90% or better, fallback rate under 5%.")
        lines.append("")
        for run in runs:
            s = run["summary"]
            if s["falseApprovals"] or s["falseRejections"]:
                lines.append(f"**{run['config']} / {run['split']}** traps approved: {', '.join(s['falseApprovals']) or 'none'}; good offers blocked: {', '.join(s['falseRejections']) or 'none'}")
                lines.append("")

    if benchmark:
        lines.append("## Before and after the speed and cost changes")
        lines.append("")
        lines.append(f"AI mode: {benchmark['aiMode']}. {benchmark['note']}")
        lines.append("")
        lines.append("| Scenario | Run | Old design: AI calls | Old design: seconds | New design: AI calls | New design: seconds |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for row in benchmark["comparison"]:
            lines.append(f"| {row['scenario']} | {row['run']} | {row['oldCalls']} | {row['oldSeconds']:.2f} | {row['newCalls']} | {row['newSeconds']:.2f} |")
        lines.append("")

    if not runs and not benchmark:
        lines.append("No results yet. Run `python -m evals.run --config offline --split dev`.")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return REPORT
