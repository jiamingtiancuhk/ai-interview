from evals import candidate
from evals.metrics import interview_metrics, one_question, turn_metrics


def t(behavior, routed, follow=False, action="next_topic", reply="下一个问题？", eligible=True, stage="technical", recent=()):
    return {
        "behavior": behavior, "expected_type": candidate.EXPECTED_TYPE[candidate.Behavior(behavior)],
        "routed_type": routed, "needs_follow_up": follow, "action": action, "reply": reply,
        "probe_eligible": eligible, "stage_kind": stage, "recent": list(recent),
        "route_s": 1.0, "first_sentence_s": 2.0,
    }


def test_turn_metrics():
    turns = [
        t("vague", "answer", follow=True, action="follow_up"),
        t("vague", "answer", follow=False),
        t("vague", "answer", follow=True, action="next_stage", eligible=False),  # cap reached: not counted at system level
        t("solid", "answer", follow=False),
        t("solid", "answer", follow=True, action="follow_up"),
        t("clarify", "clarification_request", action="clarify"),
        t("clarify", "answer", action="next_topic"),
        t("candidate_question", "candidate_question", action="answer_candidate", reply="我们用 Go。回到刚才的问题：你怎么做的？"),
        t("off_topic", "answer", action="follow_up", reply="请问你说的是什么？还有呢？"),
        t("dont_know", "dont_know", reply="", action="next_topic", recent=["你怎么保证消息不丢？"]),
    ]
    m = turn_metrics(turns)
    assert m["routing_accuracy"] == 0.8
    assert m["vague_probe_recall"] == round(2 / 3, 3)
    assert m["vague_follow_up_rate"] == 0.5
    assert m["solid_probe_rate"] == 0.5
    assert m["probe_discrimination"] == round(2 / 3 - 0.5, 3)
    assert m["clarify_handled"] == 0.5
    assert m["candidate_question_answered"] == 1.0
    assert m["candidate_question_returns_to_topic"] == 1.0
    # asking turns: 9 with question actions; the off-topic reply has two "?" and the empty one none
    assert m["one_question_rate"] == round(7 / 9, 3)
    assert m["empty_reply_rate"] == 0.1


def test_echo_detected_from_first_sentence():
    m = turn_metrics([t("solid", "answer", reply="你怎么保证消息不丢？那我们换个话题吧？", recent=["你怎么保证消息不丢？"])])
    assert m["echo_rate"] == 1.0


def test_one_question():
    assert one_question("好的。你怎么做的？")
    assert not one_question("你怎么做的？为什么？")
    assert not one_question("好的。")


def test_interview_metrics():
    ivs = [
        {"finished": True, "reached_qa": True, "elapsed_s": 900, "duration_s": 900,
         "stages": [{"spent_s": 60, "budget_s": 60}, {"spent_s": 200, "budget_s": 120}]},
        {"finished": False, "reached_qa": False, "elapsed_s": 500, "duration_s": 900,
         "stages": [{"spent_s": 70, "budget_s": 60}]},
    ]
    m = interview_metrics(ivs)
    assert m["finished_rate"] == 0.5 and m["reached_candidate_questions"] == 0.5
    assert m["stages_within_budget"] == round(2 / 3, 3)
    assert m["total_time_ratio_median"] == 1.0


def test_unfaithful_turns_excluded_from_label_metrics_only():
    bad = t("clarify", "answer", action="next_topic", reply="你好？")
    bad["faithful"] = False
    m = turn_metrics([t("clarify", "clarification_request", action="clarify"), bad])
    assert m["simulator_fidelity"] == 0.5
    assert m["clarify_handled"] == 1.0  # unfaithful turn ignored
    assert m["one_question_rate"] == 1.0 and m["turns"] == 2  # but still counted here


def test_threshold_sweep():
    from evals.metrics import threshold_sweep

    turns = [dict(behavior="vague", specificity=x) for x in (1, 2, 3)] + [dict(behavior="solid", specificity=x) for x in (3, 4, 5, 5)]
    rows = {r["threshold"]: r for r in threshold_sweep(turns)}
    assert rows[2] == {"threshold": 2, "vague": round(2 / 3, 3), "solid": 0.0, "gap": round(2 / 3, 3)}
    assert rows[3]["vague"] == 1.0 and rows[3]["solid"] == 0.25


def test_reasoning_leak_detected():
    leaks = ["首先，理解角色：我是技术负责人", "First, I need to...", "根据 DIRECTIVE，我需要", "Let me think about the role."]
    fine = ["好的。你在项目里具体负责什么？", "First things first: what did you build?", "Let me rephrase that: what did you own?",
            "Okay, let's dive into your projects."]
    m = turn_metrics([t("solid", "answer", reply=r) for r in leaks + fine])
    assert m["reasoning_leak_rate"] == round(4 / 8, 3)
