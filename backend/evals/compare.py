"""Side-by-side comparison of eval runs (first run is the reference).

    uv run python -m evals.compare baseline qwen3-4b no-guardrails
"""

import json
import sys

from .run import RESULTS

# (key, label, higher_is_better)
METRICS = [
    ("simulator_fidelity", "Simulator fidelity", True),
    ("routing_accuracy", "Routing accuracy", True),
    ("vague_probe_recall", "Vague answers flagged for follow-up", True),
    ("vague_follow_up_rate", "Vague answers followed up (when allowed)", True),
    ("solid_probe_rate", "Solid answers flagged for follow-up", None),
    ("probe_discrimination", "Probe discrimination (vague - solid)", True),
    ("clarify_handled", "Clarification requests handled", True),
    ("candidate_question_answered", "Candidate questions answered", True),
    ("candidate_question_returns_to_topic", "...then back to the open question", True),
    ("one_question_rate", "Exactly one question per turn", True),
    ("echo_rate", "Replies opening with an echo", False),
    ("reasoning_leak_rate", "Replies leaking the model's reasoning", False),
    ("finished_rate", "Interviews finished", True),
    ("stages_within_budget", "Stages within time budget", True),
    ("route_latency_p50", "Routing latency p50 (s)", False),
    ("first_sentence_p50", "First sentence p50 (s)", False),
    ("first_sentence_p95", "First sentence p95 (s)", False),
]


def fmt(v) -> str:
    if v is None:
        return "–"
    return f"{v:.0%}" if isinstance(v, float) and v <= 1 and not isinstance(v, bool) else str(v)


def compare(names: list[str]) -> str:
    runs = [json.loads((RESULTS / n / "summary.json").read_text()) for n in names]
    head = "| metric | " + " | ".join(f"{r['name']} ({r['interviewer_model']}{'' if r['guardrails'] else ', no guardrails'})" for r in runs) + " |"
    lines = [head, "|---" * (len(runs) + 1) + "|"]
    for key, label, better in METRICS:
        ref = runs[0].get(key)
        cells = []
        for r in runs:
            v = r.get(key)
            cell = fmt(v) if "latency" not in key and "sentence" not in key else ("–" if v is None else f"{v}")
            if r is not runs[0] and better is not None and isinstance(v, (int, float)) and isinstance(ref, (int, float)) and v != ref:
                cell += " ▲" if (v > ref) == better else " ▼"
            cells.append(cell)
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append(f"| Turns evaluated | " + " | ".join(str(r["turns"]) for r in runs) + " |")
    return "\n".join(lines) + "\n\n▲ better / ▼ worse than the first column.\n"


if __name__ == "__main__":
    print(compare(sys.argv[1:]))
