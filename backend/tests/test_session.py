from app.interview import planner
from app.interview.models import Action, InterviewConfig, StageKind
from app.interview.session import InterviewSession
from app.store import Store

from .fakes import FakeLLM, evaluation


async def drain(chunks) -> str:
    return "".join([c async for c in chunks])


async def new_session(llm, **cfg) -> InterviewSession:
    c = InterviewConfig(job_title="Backend Engineer", **cfg)
    plan = await planner.build_plan(llm, c, None)
    return InterviewSession(cfg=c, plan=plan, profile=None)


async def test_fallback_plan_matches_role_skeleton():
    s = await new_session(FakeLLM(), interviewer_role="hr")
    kinds = [st.kind for st in s.plan.stages]
    assert kinds == [StageKind.intro, StageKind.resume_deep_dive, StageKind.behavioral, StageKind.candidate_questions]
    assert all(st.topics for st in s.plan.stages)


async def test_follow_up_then_advance_and_transcript_tags():
    llm = FakeLLM([evaluation(should_probe=True, topic_exhausted=False, probe_angle="numbers?"), evaluation()])
    s = await new_session(llm)
    await drain(s.open(llm))

    rec, chunks = await s.answer(llm, "I built some stuff")
    await drain(chunks)
    assert rec.action == Action.follow_up
    assert s.state.stage_index == 0

    rec, chunks = await s.answer(llm, "It cut latency 40%")
    await drain(chunks)
    assert rec.action == Action.next_stage
    assert s.state.stage_index == 1

    roles = [m.role for m in s.messages]
    assert roles == ["interviewer", "candidate", "interviewer", "candidate", "interviewer"]
    # The new question belongs to the new stage; answers to the old one.
    assert s.messages[3].stage_index == 0 and s.messages[4].stage_index == 1


async def test_evaluation_sees_whole_topic_thread():
    llm = FakeLLM([evaluation(should_probe=True, topic_exhausted=False)])
    s = await new_session(llm)
    await drain(s.open(llm))
    _, c = await s.answer(llm, "first answer")
    await drain(c)
    pairs = s._topic_exchanges("second answer")
    assert [a for _, a in pairs] == ["first answer", "second answer"]


async def test_store_roundtrip(tmp_path):
    llm = FakeLLM()
    s = await new_session(llm, language="en")
    await drain(s.open(llm))
    _, c = await s.answer(llm, "hello")
    await drain(c)

    store = Store(tmp_path / "t.db")
    store.save(s)
    loaded = store.load(s.id)
    assert loaded.state == s.state
    assert [m.content for m in loaded.messages] == [m.content for m in s.messages]
    assert loaded.turns[0].evaluation == s.turns[0].evaluation
    assert loaded.elapsed_s() >= s.to_record()["elapsed_s"] - 0.01
