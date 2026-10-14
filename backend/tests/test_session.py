from app.interview import planner
from app.interview.models import Action, InterviewConfig, StageKind
from app.interview.session import InterviewSession
from app.store import Store

from .fakes import FakeLLM, routing


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
    llm = FakeLLM([routing(needs_follow_up=True, probe_angle="numbers?"), routing()])
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
    llm = FakeLLM([routing(needs_follow_up=True)])
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
    assert loaded.turns[0].routing == s.turns[0].routing
    assert loaded.elapsed_s() >= s.to_record()["elapsed_s"] - 0.01


async def test_reply_is_cut_after_first_question_and_label_stripped():
    llm = FakeLLM(replies=[["面试官：", "你好，我是", "技术负责人。", "先做个自我介绍吧？", "另外你为什么", "离职？"]])
    s = await new_session(llm)
    said = await drain(s.open(llm))
    assert said == "你好，我是技术负责人。先做个自我介绍吧？"
    assert s.messages[-1].content == said
    assert llm.stream_closed == 1  # generation aborted, not drained


async def test_wrap_up_is_not_cut_and_english_keeps_spaces():
    llm = FakeLLM(replies=[["Thanks for your time. ", "Any questions? ", "We will be in touch."]])
    s = await new_session(llm, language="en")
    said = await drain(s._speak(llm, Action.wrap_up))
    assert said == "Thanks for your time. Any questions? We will be in touch."


async def test_echoed_question_is_dropped():
    llm = FakeLLM(
        routings=[routing(answer_type="candidate_question")],
        replies=[
            ["你好。", "请介绍一下你自己？"],
            ["你们团队现在主要用什么技术栈？", "我们主要用 Go 和 Kafka。", "还有其他问题吗？"],
        ],
    )
    s = await new_session(llm)
    await drain(s.open(llm))
    _, chunks = await s.answer(llm, "你们团队现在主要用什么技术栈？")
    assert await drain(chunks) == "我们主要用 Go 和 Kafka。还有其他问题吗？"


async def test_all_echo_falls_back_to_saying_something():
    llm = FakeLLM(routings=[routing(answer_type="clarification_request")],
                  replies=[["请介绍一下你自己？"], ["请介绍一下你自己？"]])
    s = await new_session(llm)
    await drain(s.open(llm))
    _, chunks = await s.answer(llm, "什么意思？")
    assert await drain(chunks) == "请介绍一下你自己？"


async def test_background_assessment_fills_turns_once():
    llm = FakeLLM([routing(), routing(answer_type="candidate_question")])
    s = await new_session(llm)
    await drain(s.open(llm))
    for text in ["answer one", "what is the team like?"]:
        _, c = await s.answer(llm, text)
        await drain(c)
    assert await s.assess_pending(llm) == 1  # candidate questions are not scored
    assert s.turns[0].assessment is not None and s.turns[1].assessment is None
    assert await s.assess_pending(llm) == 0


async def test_mid_interview_candidate_question_returns_to_open_question():
    llm = FakeLLM(
        routings=[routing(answer_type="candidate_question")],
        replies=[["你好。", "你怎么保证消息不丢？"], ["我们用 Go。"]],
    )
    s = await new_session(llm)
    await drain(s.open(llm))
    _, chunks = await s.answer(llm, "你们用什么语言？")
    assert await drain(chunks) == "我们用 Go。那我们回到刚才的问题：你怎么保证消息不丢？"
