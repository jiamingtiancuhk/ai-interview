"""Turn policy: decides what the interviewer does next.

Deliberately plain code rather than another LLM call. The LLM judges *what*
the answer contained (Routing); this module decides *where the interview
goes*, so pacing and stage transitions are predictable and unit-testable.
"""

from dataclasses import dataclass

from .models import Action, AnswerType, InterviewPlan, InterviewState, Routing, StageKind

# Follow-ups allowed on one topic before moving on. The self-introduction
# is a warm-up: one follow-up at most, then into the real content.
FOLLOW_UP_CAP = {
    StageKind.intro: 1,
    StageKind.behavioral: 2,
}


# Candidate questions answered in a row before the interviewer moves on: mid
# interview it treats the next one as an answer (protects against loops from
# misrouted answers); in the Q&A stage it wraps up.
MAX_CANDIDATE_QUESTIONS_IN_ROW = 2
MAX_QA_QUESTIONS = 3


@dataclass(frozen=True)
class Decision:
    action: Action
    state: InterviewState


def _advance_topic(plan: InterviewPlan, state: InterviewState, elapsed_s: float) -> Decision:
    stage = plan.stages[state.stage_index]
    if state.topic_index + 1 < len(stage.topics):
        new = state.model_copy(update={"topic_index": state.topic_index + 1, "follow_ups": 0})
        return Decision(Action.next_topic, new)
    return _advance_stage(plan, state, elapsed_s)


def _advance_stage(plan: InterviewPlan, state: InterviewState, elapsed_s: float) -> Decision:
    if state.stage_index + 1 < len(plan.stages):
        new = InterviewState(stage_index=state.stage_index + 1, stage_started_s=elapsed_s)
        return Decision(Action.next_stage, new)
    return Decision(Action.wrap_up, state.model_copy(update={"finished": True}))


def decide(
    plan: InterviewPlan,
    state: InterviewState,
    routing: Routing,
    elapsed_s: float,
    total_budget_s: float,
    max_follow_ups: int,
) -> Decision:
    d = _decide(plan, state, routing, elapsed_s, total_budget_s, max_follow_ups)
    streak = state.candidate_question_streak + 1 if d.action == Action.answer_candidate else 0
    return Decision(d.action, d.state.model_copy(update={"candidate_question_streak": streak}))


def _decide(
    plan: InterviewPlan,
    state: InterviewState,
    routing: Routing,
    elapsed_s: float,
    total_budget_s: float,
    max_follow_ups: int,
) -> Decision:
    stage = plan.stages[state.stage_index]
    in_qa = stage.kind == StageKind.candidate_questions
    kind = routing.answer_type

    # Questions from the candidate are answered, even when time is up, within limits.
    if kind == AnswerType.candidate_question:
        if in_qa and state.candidate_question_streak >= MAX_QA_QUESTIONS:
            return Decision(Action.wrap_up, state.model_copy(update={"finished": True}))
        if in_qa or state.candidate_question_streak < MAX_CANDIDATE_QUESTIONS_IN_ROW:
            return Decision(Action.answer_candidate, state)
        kind = AnswerType.answer  # likely a misrouted answer: carry on with the interview

    if elapsed_s >= total_budget_s:
        # Out of time: skip straight to the candidate's Q&A if we have not
        # had it yet, otherwise close.
        qa_index = next((i for i, s in enumerate(plan.stages) if s.kind == StageKind.candidate_questions), None)
        if qa_index is not None and state.stage_index < qa_index:
            return Decision(Action.next_stage, InterviewState(stage_index=qa_index, stage_started_s=elapsed_s))
        return Decision(Action.wrap_up, state.model_copy(update={"finished": True}))

    if kind == AnswerType.clarification_request:
        return Decision(Action.clarify, state)

    if in_qa:
        # Candidate answered "do you have questions?" with something other
        # than a question: they are done.
        return Decision(Action.wrap_up, state.model_copy(update={"finished": True}))

    if elapsed_s - state.stage_started_s >= stage.minutes * 60:
        return _advance_stage(plan, state, elapsed_s)

    cap = min(max_follow_ups, FOLLOW_UP_CAP.get(stage.kind, max_follow_ups))
    wants_probe = kind == AnswerType.off_topic or (kind == AnswerType.answer and routing.needs_follow_up)
    if wants_probe and state.follow_ups < cap:
        return Decision(Action.follow_up, state.model_copy(update={"follow_ups": state.follow_ups + 1}))

    return _advance_topic(plan, state, elapsed_s)
