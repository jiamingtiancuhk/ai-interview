"""Recompute summary.json/.md for saved runs from their JSONL logs (after
adding or changing a metric), without re-running any model.

    uv run python -m evals.rescore baseline improved qwen3-4b
"""

import argparse
import json

from . import metrics
from .run import RESULTS, to_markdown


def rescore(name: str) -> dict:
    out = RESULTS / name
    turns = [json.loads(line) for line in (out / "turns.jsonl").open()]
    interviews = [json.loads(line) for line in (out / "interviews.jsonl").open()]
    old = json.loads((out / "summary.json").read_text())
    keep = {k: old[k] for k in ("name", "interviewer_model", "candidate_model", "guardrails", "seed", "wall_time_s")}
    summary = {**keep, **metrics.turn_metrics(turns), **metrics.interview_metrics(interviews)}
    # Conservative variant: label metrics over every turn, including ones the verifier rejected.
    all_turns = [{**t, "faithful": True} for t in turns]
    summary["all_turns"] = {k: v for k, v in metrics.turn_metrics(all_turns).items() if not isinstance(v, (dict, list))}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (out / "summary.md").write_text(to_markdown(summary))
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+")
    for n in ap.parse_args().names:
        s = rescore(n)
        print(n, "ok", "leak", s["reasoning_leak_rate"])
