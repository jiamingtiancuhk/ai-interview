from app.interview.models import (
    Action,
    AnswerType,
    Evaluation,
    InterviewPlan,
    InterviewState,
    Scores,
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


def ev(kind=AnswerType.answer, probe=False, exhausted=False) -> Evaluation:
    return Evaluation(
        answer_type=kind,
        scores=Scores(relevance=3, depth=3, evidence=3, clarity=3, structure=3),
        strengths=[], gaps=[], vague_claims=[],
        should_probe=probe, probe_angle="why?" if probe else "", topic_exhausted=exhausted,
    )


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


def test_exhausted_topic_moves_on_even_if_probe():
    d = run(InterviewState(stage_index=1), ev(probe=True, exhausted=True))
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
