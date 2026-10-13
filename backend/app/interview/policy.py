"""Turn policy: decides what the interviewer does next.

Deliberately plain code rather than another LLM call. The LLM judges *what*
the answer contained (Evaluation); this module decides *where the interview
goes*, so pacing and stage transitions are predictable and unit-testable.
"""

from dataclasses import dataclass

from .models import Action, AnswerType, Evaluation, InterviewPlan, InterviewState, StageKind


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
    evaluation: Evaluation,
    elapsed_s: float,
    total_budget_s: float,
    max_follow_ups: int,
) -> Decision:
    stage = plan.stages[state.stage_index]
    in_qa = stage.kind == StageKind.candidate_questions
    kind = evaluation.answer_type

    # Questions from the candidate are always answered; the clock does not
    # cut someone off mid-question.
    if kind == AnswerType.candidate_question:
        return Decision(Action.answer_candidate, state)

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

    can_probe = state.follow_ups < max_follow_ups
    if kind == AnswerType.off_topic and can_probe:
        return Decision(Action.follow_up, state.model_copy(update={"follow_ups": state.follow_ups + 1}))

    if (
        kind == AnswerType.answer
        and evaluation.should_probe
        and not evaluation.topic_exhausted
        and can_probe
    ):
        return Decision(Action.follow_up, state.model_copy(update={"follow_ups": state.follow_ups + 1}))

    return _advance_topic(plan, state, elapsed_s)
