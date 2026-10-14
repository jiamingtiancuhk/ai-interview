"""Error analysis for a run: confusion matrix and examples of each failure type.

    uv run python -m evals.inspect_errors baseline [--examples 3]
"""

import argparse
import json
from collections import Counter, defaultdict

from .metrics import QUESTION_ACTIONS, one_question
from .run import RESULTS


def main(name: str, examples: int) -> None:
    turns = [json.loads(line) for line in (RESULTS / name / "turns.jsonl").open()]
    faithful = [t for t in turns if t.get("faithful", True)]

    print("## Routing confusion (intended behavior -> routed type)\n")
    conf = Counter((t["behavior"], t["routed_type"]) for t in faithful)
    for (b, r), n in sorted(conf.items()):
        mark = "" if r == t_expected(b) else "  <-- wrong"
        print(f"{b:20s} -> {r:24s} {n:3d}{mark}")

    groups: dict[str, list[dict]] = defaultdict(list)
    for t in faithful:
        if t["routed_type"] != t["expected_type"]:
            groups[f"routing: {t['behavior']} -> {t['routed_type']}"].append(t)
        if t["behavior"] == "vague" and t["probe_eligible"] and t["action"] != "follow_up":
            groups["vague answer not followed up"].append(t)
    for t in turns:
        if t["action"] in QUESTION_ACTIONS and not one_question(t["reply"]):
            groups["reply not exactly one question"].append(t)

    for g, ts in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        print(f"\n## {g} ({len(ts)})\n")
        for t in ts[:examples]:
            print(f"[{t['scenario']}/{t['persona']} #{t['turn']} stage={t['stage_kind']} action={t['action']}]")
            print(f"  Q: {t['question'][:200]}")
            print(f"  A: {t['answer'][:200]}")
            print(f"  I: {t['reply'][:200]}\n")


def t_expected(behavior: str) -> str:
    from .candidate import EXPECTED_TYPE, Behavior

    return EXPECTED_TYPE[Behavior(behavior)]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--examples", type=int, default=3)
    a = ap.parse_args()
    main(a.name, a.examples)
