from app.interview.models import (
    Action,
    AnswerType,
    InterviewPlan,
    InterviewState,
    Routing,
    Stage,
    StageKind,
    Topic,
)
from app.interview.policy import decide

T = Topic(title="t", rationale="", opening_question="q?")
PLAN = InterviewPlan(
    stages=[
        Stage(kind=StageKind.intro, goal="", minutes=3, topics=[T]),
        Stage(kind=StageKind.technical, goal="", minutes=10, topics=[T, T]),
        Stage(kind=StageKind.candidate_questions, goal="", minutes=3, topics=[T]),
    ]
)
BUDGET = 30 * 60


def ev(kind=AnswerType.answer, probe=False) -> Routing:
    c = not probe
    return Routing(answer_type=kind, missing="why?" if probe else "", concrete=c, own_actions=c, numbers=c, reasoning=c)


def run(state, evaluation, elapsed=60.0, max_fu=2):
    return decide(PLAN, state, evaluation, elapsed, BUDGET, max_fu)


def test_probes_vague_answer():
    d = run(InterviewState(stage_index=1), ev(probe=True))
    assert d.action == Action.follow_up
    assert d.state.follow_ups == 1


def test_follow_up_cap_moves_on():
    d = run(InterviewState(stage_index=1, follow_ups=2), ev(probe=True))
    assert d.action == Action.next_topic
    assert (d.state.topic_index, d.state.follow_ups) == (1, 0)


def test_complete_answer_moves_on():
    d = run(InterviewState(stage_index=1), ev(probe=False))
    assert d.action == Action.next_topic


def test_intro_allows_only_one_follow_up():
    assert run(InterviewState(stage_index=0), ev(probe=True)).action == Action.follow_up
    d = run(InterviewState(stage_index=0, follow_ups=1), ev(probe=True))
    assert d.action == Action.next_stage


def test_off_topic_is_redirected_then_dropped():
    assert run(InterviewState(stage_index=1), ev(AnswerType.off_topic)).action == Action.follow_up
    d = run(InterviewState(stage_index=1, follow_ups=2), ev(AnswerType.off_topic))
    assert d.action == Action.next_topic


def test_last_topic_advances_stage_and_resets_clock():
    d = run(InterviewState(stage_index=1, topic_index=1), ev(), elapsed=400)
    assert d.action == Action.next_stage
    assert d.state.stage_index == 2 and d.state.stage_started_s == 400


def test_clarification_keeps_state():
    s = InterviewState(stage_index=1, follow_ups=1)
    d = run(s, ev(AnswerType.clarification_request))
    assert d.action == Action.clarify and d.state == s


def test_candidate_question_answered_even_when_out_of_time():
    s = InterviewState(stage_index=2)
    d = run(s, ev(AnswerType.candidate_question), elapsed=BUDGET + 60)
    assert d.action == Action.answer_candidate


def test_dont_know_moves_on():
    d = run(InterviewState(stage_index=1), ev(AnswerType.dont_know))
    assert d.action == Action.next_topic


def test_stage_overrun_advances_stage():
    s = InterviewState(stage_index=1, stage_started_s=0)
    d = run(s, ev(probe=True), elapsed=10 * 60 + 1)
    assert d.action == Action.next_stage


def test_out_of_time_jumps_to_candidate_questions():
    d = run(InterviewState(stage_index=1), ev(probe=True), elapsed=BUDGET)
    assert d.action == Action.next_stage and d.state.stage_index == 2


def test_out_of_time_in_qa_wraps_up():
    d = run(InterviewState(stage_index=2), ev(), elapsed=BUDGET)
    assert d.action == Action.wrap_up and d.state.finished


def test_no_more_questions_wraps_up():
    d = run(InterviewState(stage_index=2), ev(AnswerType.answer))
    assert d.action == Action.wrap_up and d.state.finished


def test_misrouted_answers_cannot_loop_on_candidate_questions():
    s = InterviewState(stage_index=1)
    d1 = run(s, ev(AnswerType.candidate_question))
    d2 = run(d1.state, ev(AnswerType.candidate_question))
    assert (d1.action, d2.action) == (Action.answer_candidate, Action.answer_candidate)
    d3 = run(d2.state, ev(AnswerType.candidate_question))
    assert d3.action != Action.answer_candidate  # third in a row is treated as an answer
    assert d3.state.candidate_question_streak == 0


def test_qa_stage_wraps_up_after_enough_questions():
    s = InterviewState(stage_index=2)
    for _ in range(3):
        d = run(s, ev(AnswerType.candidate_question))
        assert d.action == Action.answer_candidate
        s = d.state
    assert run(s, ev(AnswerType.candidate_question)).action == Action.wrap_up


def test_follow_up_threshold_applies_to_specificity():
    from app.interview.models import FOLLOW_UP_AT_OR_BELOW

    checks = ["concrete", "own_actions", "numbers", "reasoning"]

    def with_n(n):
        return Routing(answer_type="answer", missing="", **{c: i < n for i, c in enumerate(checks)})

    assert with_n(FOLLOW_UP_AT_OR_BELOW).needs_follow_up
    assert not with_n(FOLLOW_UP_AT_OR_BELOW + 1).needs_follow_up
    assert with_n(3).specificity == 3
    props = Routing.model_json_schema()["properties"]
    assert "needs_follow_up" not in props and "specificity" not in props  # code decides, not the LLM
