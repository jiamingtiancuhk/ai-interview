from collections.abc import AsyncIterator

from app.interview.models import CandidateProfile, Evaluation, InterviewPlan, Scores


def evaluation(**overrides) -> Evaluation:
    base = dict(
        answer_type="answer",
        scores=Scores(relevance=3, depth=3, evidence=3, clarity=3, structure=3),
        strengths=[], gaps=[], vague_claims=[],
        should_probe=False, probe_angle="", topic_exhausted=True,
    )
    return Evaluation(**{**base, **overrides})


class FakeLLM:
    """Scripted LLM: structured() pops queued objects, stream() echoes the directive."""

    def __init__(self, evaluations: list[Evaluation] | None = None, plan: InterviewPlan | None = None):
        self.evaluations = list(evaluations or [])
        self.plan = plan or InterviewPlan(stages=[])
        self.calls: list[str] = []

    async def structured(self, messages, schema, temperature=0.2):
        self.calls.append(schema.__name__)
        if schema is Evaluation:
            return self.evaluations.pop(0) if self.evaluations else evaluation()
        if schema is InterviewPlan:
            return self.plan
        if schema is CandidateProfile:
            return CandidateProfile(seniority_guess="mid", key_skills=["python"], projects=[], jd_requirements=[], gaps=[])
        raise AssertionError(schema)

    async def stream(self, messages, temperature=0.7) -> AsyncIterator[str]:
        directive = messages[-1]["content"]
        for word in directive.split(" ")[:6]:
            yield word + " "
