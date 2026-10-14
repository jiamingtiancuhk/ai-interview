from collections.abc import AsyncIterator

from app.interview.models import Assessment, CandidateProfile, Improvement, InterviewPlan, Report, Routing, Scores, StageFeedback


def routing(needs_follow_up: bool = False, probe_angle: str = "", **overrides) -> Routing:
    checks = not needs_follow_up
    base = {"answer_type": "answer", "missing": probe_angle, "concrete": checks, "own_actions": checks, "numbers": checks, "reasoning": checks}
    return Routing(**{**base, **overrides})


def assessment() -> Assessment:
    return Assessment(
        scores=Scores(relevance=3, depth=2, evidence=2, clarity=4, structure=3),
        strengths=["clear"], gaps=["no numbers"], vague_claims=[], better_answer_hint="add metrics",
    )


class FakeLLM:
    """Scripted LLM. structured() pops queued routings; stream() replays `replies`
    (or the directive's first words) chunk by chunk."""

    def __init__(self, routings: list[Routing] | None = None, replies: list[list[str]] | None = None,
                 plan: InterviewPlan | None = None):
        self.routings = list(routings or [])
        self.replies = list(replies or [])
        self.plan = plan or InterviewPlan(stages=[])
        self.calls: list[str] = []
        self.stream_closed = 0

    async def structured(self, messages, schema, temperature=0.2):
        self.calls.append(schema.__name__)
        if schema is Routing:
            return self.routings.pop(0) if self.routings else routing()
        if schema is Assessment:
            return assessment()
        if schema is Report:
            return Report(
                recommendation="lean_yes", summary="ok",
                stages=[StageFeedback(kind="intro", score=3, comment="fine")],
                strengths=["clear"], improvements=[Improvement(issue="no numbers", how_to_practice="add metrics")],
            )
        if schema is InterviewPlan:
            return self.plan
        if schema is CandidateProfile:
            return CandidateProfile(seniority_guess="mid", key_skills=["python"], projects=[], jd_requirements=[], gaps=[])
        raise AssertionError(schema)

    async def stream(self, messages, temperature=0.7) -> AsyncIterator[str]:
        if self.replies:
            chunks = self.replies.pop(0)
        else:
            directive = messages[-1]["content"].split("DIRECTIVE: ")[-1]
            chunks = [w + " " for w in directive.split(" ")[:6]] + ["?"]
        try:
            for c in chunks:
                yield c
        finally:
            self.stream_closed += 1
