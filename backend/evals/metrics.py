"""Metrics over eval logs. Pure functions of the JSONL records written by
evals.run, so a finished run can be re-scored without re-running models."""

import re
import statistics
from collections import Counter, defaultdict

from app.interview.session import _SENTENCE_END, _is_echo, _norm

QUESTION_ACTIONS = {"follow_up", "clarify", "next_topic", "next_stage"}
_QMARK = re.compile(r"[?？]")


def _rate(hits: int, total: int) -> float | None:
    return round(hits / total, 3) if total else None


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values) - 1, int(q * len(values)))], 2)


def first_sentence(text: str) -> str:
    m = _SENTENCE_END.search(text)
    return text[: m.end()] if m else text


def one_question(reply: str) -> bool:
    return len(_QMARK.findall(reply)) == 1 and reply.rstrip().endswith(("?", "？"))


def turn_metrics(all_turns: list[dict]) -> dict:
    # Label metrics only use turns where the simulated candidate verifiably did
    # what it was told; otherwise the "ground truth" itself would be wrong.
    turns = [t for t in all_turns if t.get("faithful", True)]
    by_behavior: dict[str, list[dict]] = defaultdict(list)
    for t in turns:
        by_behavior[t["behavior"]].append(t)

    vague, solid = by_behavior["vague"], by_behavior["solid"]
    vague_eligible = [t for t in vague if t["probe_eligible"]]
    clarify, cq = by_behavior["clarify"], by_behavior["candidate_question"]
    asking = [t for t in all_turns if t["action"] in QUESTION_ACTIONS]
    mid_cq = [t for t in cq if t["stage_kind"] != "candidate_questions"]

    recall = _rate(sum(t["needs_follow_up"] for t in vague), len(vague))
    solid_probe = _rate(sum(t["needs_follow_up"] for t in solid), len(solid))
    return {
        "turns": len(all_turns),
        "simulator_fidelity": _rate(len(turns), len(all_turns)),
        # Did routing label the answer type the candidate actually produced?
        "routing_accuracy": _rate(sum(t["routed_type"] == t["expected_type"] for t in turns), len(turns)),
        "routing_accuracy_by_behavior": {
            b: _rate(sum(t["routed_type"] == t["expected_type"] for t in ts), len(ts)) for b, ts in sorted(by_behavior.items())
        },
        # Vague answers flagged for a follow-up (routing level) ...
        "vague_probe_recall": recall,
        # ... and actually followed up when the policy allowed it (system level).
        "vague_follow_up_rate": _rate(sum(t["action"] == "follow_up" for t in vague_eligible), len(vague_eligible)),
        # Strong answers flagged for follow-up. Not always wrong (good interviewers dig into good
        # answers too), so the headline is the gap between the two.
        "solid_probe_rate": solid_probe,
        "probe_discrimination": round(recall - solid_probe, 3) if recall is not None and solid_probe is not None else None,
        "clarify_handled": _rate(sum(t["action"] == "clarify" for t in clarify), len(clarify)),
        "candidate_question_answered": _rate(sum(t["action"] == "answer_candidate" for t in cq), len(cq)),
        "candidate_question_returns_to_topic": _rate(
            sum(t["action"] == "answer_candidate" and t["reply"].rstrip().endswith(("?", "？")) for t in mid_cq), len(mid_cq)
        ),
        "one_question_rate": _rate(sum(one_question(t["reply"]) for t in asking), len(asking)),
        # Label-independent metrics use every turn.
        "echo_rate": _rate(sum(_is_echo(first_sentence(t["reply"]), [_norm(x) for x in t["recent"]]) for t in all_turns), len(all_turns)),
        "empty_reply_rate": _rate(sum(not t["reply"].strip() for t in all_turns), len(all_turns)),
        "route_latency_p50": _pct([t["route_s"] for t in all_turns], 0.5),
        "route_latency_p95": _pct([t["route_s"] for t in all_turns], 0.95),
        "first_sentence_p50": _pct([t["first_sentence_s"] for t in all_turns if t["first_sentence_s"] is not None], 0.5),
        "first_sentence_p95": _pct([t["first_sentence_s"] for t in all_turns if t["first_sentence_s"] is not None], 0.95),
        "behaviors": dict(Counter(t["behavior"] for t in all_turns)),
        "threshold_sweep": threshold_sweep(turns),
    }


def threshold_sweep(turns: list[dict]) -> list[dict]:
    """Probe rates on vague vs solid answers for every specificity threshold,
    to choose FOLLOW_UP_AT_OR_BELOW from data rather than by feel."""
    graded = [t for t in turns if t.get("specificity") is not None and t["behavior"] in ("vague", "solid")]
    vague = [t["specificity"] for t in graded if t["behavior"] == "vague"]
    solid = [t["specificity"] for t in graded if t["behavior"] == "solid"]
    if not vague or not solid:
        return []
    rows = []
    for th in range(1, 5):
        v = _rate(sum(x <= th for x in vague), len(vague))
        so = _rate(sum(x <= th for x in solid), len(solid))
        rows.append({"threshold": th, "vague": v, "solid": so, "gap": round(v - so, 3)})
    return rows


def interview_metrics(interviews: list[dict]) -> dict:
    stage_ratios = [st["spent_s"] / st["budget_s"] for iv in interviews for st in iv["stages"] if st["budget_s"]]
    return {
        "interviews": len(interviews),
        "finished_rate": _rate(sum(iv["finished"] for iv in interviews), len(interviews)),
        "reached_candidate_questions": _rate(sum(iv["reached_qa"] for iv in interviews), len(interviews)),
        # A stage may overrun by the answer in progress when its time runs out; 1.25x allows for that.
        "stages_within_budget": _rate(sum(r <= 1.25 for r in stage_ratios), len(stage_ratios)),
        "stage_time_ratio_median": round(statistics.median(stage_ratios), 2) if stage_ratios else None,
        "total_time_ratio_median": round(
            statistics.median(iv["elapsed_s"] / iv["duration_s"] for iv in interviews if iv["finished"]), 2
        )
        if any(iv["finished"] for iv in interviews)
        else None,
    }
