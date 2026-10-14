"""Run simulated interviews against the real interview engine and score them.

    uv run python -m evals.run --name baseline
    uv run python -m evals.run --model qwen3:4b --name qwen3-4b
    uv run python -m evals.run --no-guardrails --name no-guardrails
    uv run python -m evals.run --quick            # 2 scenarios, short interviews

Writes evals/results/<name>/{turns,interviews}.jsonl and summary.json/.md.
"""

import argparse
import asyncio
import copy
import json
import logging
import time
from pathlib import Path

from app import config
from app.interview import planner, policy
from app.interview.session import InterviewSession
from app.llm import OllamaLLM

from . import candidate, metrics
from .scenarios import SCENARIOS

RESULTS = Path(__file__).parent / "results"
log = logging.getLogger("evals")


class VirtualClock:
    """Interview time advances by estimated speaking time, not wall time."""

    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def speak(self, text: str, language: str) -> None:
        seconds = len(text) / 4.5 if language == "zh" else len(text.split()) / 2.6
        self.t += seconds + 1.5  # plus a short pause between turns


async def run_interview(
    interviewer, cand, scenario: str, persona_name: str, plan, profile, args, out_turns
) -> dict:
    cfg = SCENARIOS[scenario]
    clock = VirtualClock()
    s = InterviewSession(cfg=cfg, plan=copy.deepcopy(plan), profile=profile, clock=clock, guardrails=not args.no_guardrails)
    opening = "".join([c async for c in s.open(interviewer)])
    clock.speak(opening, cfg.language)
    behaviors = candidate.schedule(candidate.PERSONAS[persona_name], args.max_turns, args.seed)

    qa_questions = 0
    for i, behavior in enumerate(behaviors):
        # In the Q&A stage only two behaviors make sense: ask one question, then none.
        if s.stage.kind == "candidate_questions":
            behavior = candidate.Behavior.candidate_question if qa_questions == 0 else candidate.Behavior.no_more_questions
            qa_questions += behavior == candidate.Behavior.candidate_question
        transcript = [(m.role, m.content) for m in s.messages]
        text, faithful = await candidate.answer(cand, cfg, transcript, behavior)
        clock.speak(text, cfg.language)

        # Could the policy follow up at all on this turn (cap left, stage and
        # interview not out of time)? Needed to score system-level follow-ups.
        stage = s.stage
        cap = min(config.MAX_FOLLOW_UPS, policy.FOLLOW_UP_CAP.get(stage.kind, config.MAX_FOLLOW_UPS))
        elapsed = s.elapsed_s()
        eligible = (
            s.state.follow_ups < cap
            and elapsed - s.state.stage_started_s < stage.minutes * 60
            and elapsed < cfg.duration_min * 60
            and stage.kind != "candidate_questions"
        )
        recent = [m.content for m in s.messages[-2:]] + [text]

        t0 = time.perf_counter()
        record, chunks = await s.answer(interviewer, text)
        first, parts = None, []
        async for piece in chunks:
            first = first if first is not None else time.perf_counter() - t0
            parts.append(piece)
        reply = "".join(parts)
        clock.speak(reply, cfg.language)

        out_turns.append({
            "scenario": scenario, "persona": persona_name, "turn": i,
            "behavior": behavior.value, "expected_type": candidate.EXPECTED_TYPE[behavior], "faithful": faithful,
            "routed_type": record.routing.answer_type.value, "needs_follow_up": record.routing.needs_follow_up,
            "specificity": getattr(record.routing, "specificity", None),
            "probe_angle": record.routing.probe_angle, "action": record.action.value,
            "stage_kind": stage.kind.value,
            "probe_eligible": eligible, "question": record.question, "answer": text, "reply": reply,
            "recent": recent, "route_s": record.route_latency_s,
            "first_sentence_s": round(first, 2) if first is not None else None,
            "elapsed_s": round(clock.t, 1),
        })
        log.info("%s/%s #%d %s -> %s / %s", scenario, persona_name, i, behavior, record.routing.answer_type, record.action)
        if s.state.finished:
            break

    # Time spent per stage, from the first message tagged with it to the next stage.
    starts: dict[int, float] = {}
    for m in s.messages:
        starts.setdefault(m.stage_index, m.elapsed_s)
    order = sorted(starts)
    stages = []
    for j, idx in enumerate(order[:-1] if not s.state.finished else order):
        end = starts[order[j + 1]] if j + 1 < len(order) else clock.t
        stages.append({"kind": s.plan.stages[idx].kind.value, "spent_s": round(end - starts[idx], 1),
                       "budget_s": s.plan.stages[idx].minutes * 60})
    return {
        "scenario": scenario, "persona": persona_name, "finished": s.state.finished,
        "reached_qa": any(s.plan.stages[i].kind == "candidate_questions" for i in starts),
        "turns": len(s.turns), "elapsed_s": round(clock.t, 1), "duration_s": cfg.duration_min * 60, "stages": stages,
    }


def write_summary(out: Path, args, turns: list[dict], interviews: list[dict], wall_s: float) -> dict:
    summary = {
        "name": args.name, "interviewer_model": args.model, "candidate_model": args.candidate_model,
        "guardrails": not args.no_guardrails, "seed": args.seed, "wall_time_s": round(wall_s),
        **metrics.turn_metrics(turns), **metrics.interview_metrics(interviews),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (out / "summary.md").write_text(to_markdown(summary))
    return summary


def to_markdown(s: dict) -> str:
    rows = [(k, v) for k, v in s.items() if not isinstance(v, dict)]
    lines = [f"# Eval: {s['name']}", "", "| metric | value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in rows]
    lines += ["", "Routing accuracy by behavior:", ""]
    lines += [f"- {b}: {v}" for b, v in s["routing_accuracy_by_behavior"].items()]
    if s.get("threshold_sweep"):
        lines += ["", "Follow-up threshold sweep (follow up when specificity <= t):", "",
                  "| t | vague followed up | solid followed up | gap |", "|---|---|---|---|"]
        lines += [f"| {r['threshold']} | {r['vague']} | {r['solid']} | {r['gap']} |" for r in s["threshold_sweep"]]
    return "\n".join(lines) + "\n"


async def main(args) -> None:
    out = RESULTS / args.name
    out.mkdir(parents=True, exist_ok=True)
    interviewer = OllamaLLM(model=args.model)
    cand = OllamaLLM(model=args.candidate_model)
    scenarios = args.scenarios or (["backend_zh", "frontend_en"] if args.quick else list(SCENARIOS))
    personas = args.personas or list(candidate.PERSONAS)

    turns: list[dict] = []
    interviews: list[dict] = []
    t0 = time.perf_counter()
    for sc in scenarios:
        cfg = SCENARIOS[sc]
        profile = await planner.build_profile(interviewer, cfg)
        plan = await planner.build_plan(interviewer, cfg, profile)
        for p in personas:
            interviews.append(await run_interview(interviewer, cand, sc, p, plan, profile, args, turns))
            # Write as we go so a long run can be inspected (and survives a crash).
            (out / "turns.jsonl").write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in turns))
            (out / "interviews.jsonl").write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in interviews))
    summary = write_summary(out, args, turns, interviews, time.perf_counter() - t0)
    print(to_markdown(summary))
    await interviewer.aclose()
    await cand.aclose()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="baseline")
    ap.add_argument("--model", default=config.LLM_MODEL, help="interviewer model")
    ap.add_argument("--candidate-model", default="qwen3:8b", help="kept fixed across comparisons")
    ap.add_argument("--scenarios", nargs="*", choices=list(SCENARIOS))
    ap.add_argument("--personas", nargs="*", choices=list(candidate.PERSONAS))
    ap.add_argument("--max-turns", type=int, default=14)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-guardrails", action="store_true")
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    if args.quick:
        args.max_turns = min(args.max_turns, 8)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(main(args))
