import logging

from ..llm import LLM
from . import prompts
from .models import CandidateProfile, InterviewConfig, InterviewPlan, Stage, StageKind, Topic

log = logging.getLogger(__name__)

_FALLBACK_Q = {
    "zh": {
        StageKind.intro: "先请你做一个简单的自我介绍吧，重点讲讲和这个岗位相关的经历。",
        StageKind.resume_deep_dive: "挑一个你最有代表性的项目，讲讲你在里面具体负责什么。",
        StageKind.technical: "说说你在这个岗位相关的技术里最熟悉的一块，以及你踩过的一个坑。",
        StageKind.behavioral: "讲一次你和同事意见不一致的经历，最后是怎么解决的？",
        StageKind.candidate_questions: "我这边的问题差不多了，你有什么想问我的吗？",
    },
    "en": {
        StageKind.intro: "To start, could you briefly introduce yourself, focusing on what's relevant to this role?",
        StageKind.resume_deep_dive: "Pick the project you're most proud of and walk me through what you personally owned.",
        StageKind.technical: "Which technical area relevant to this role do you know best, and what's a hard problem you hit there?",
        StageKind.behavioral: "Tell me about a time you disagreed with a teammate. How did it get resolved?",
        StageKind.candidate_questions: "That's all from my side. Do you have any questions for me?",
    },
}


async def build_profile(llm: LLM, cfg: InterviewConfig) -> CandidateProfile | None:
    if not (cfg.resume_text.strip() or cfg.job_description.strip()):
        return None
    return await llm.structured(prompts.profile_messages(cfg), CandidateProfile)


def normalize(plan: InterviewPlan, cfg: InterviewConfig) -> InterviewPlan:
    """Force the LLM's plan onto the skeleton: right stages, order, budgets.

    Small models occasionally drop or reorder stages; the skeleton is the
    source of truth and the LLM only contributes topics.
    """
    by_kind = {s.kind: s for s in plan.stages}
    fixed = []
    for kind, minutes, n_topics in prompts.skeleton(cfg):
        kind = StageKind(kind)
        src = by_kind.get(kind)
        topics = list(src.topics[:n_topics]) if src else []
        if not topics:
            q = _FALLBACK_Q[cfg.language][kind]
            topics = [Topic(title=kind.value, rationale="", opening_question=q)]
        goal = src.goal if src else prompts.STAGE_DESC[kind]
        fixed.append(Stage(kind=kind, goal=goal, minutes=minutes, topics=topics))
    return InterviewPlan(stages=fixed)


def skeleton_plan(cfg: InterviewConfig) -> InterviewPlan:
    """Stages and budgets with generic questions; available instantly."""
    return normalize(InterviewPlan(stages=[]), cfg)


_ROLE_INTRO = {
    "zh": {"tech_lead": "团队的技术负责人", "hiring_manager": "这个岗位的业务主管", "hr": "负责招聘的 HR"},
    "en": {"tech_lead": "the tech lead of the team", "hiring_manager": "the hiring manager for this role", "hr": "from the recruiting team"},
}


def opening_line(cfg: InterviewConfig) -> str:
    """Templated greeting so the interview starts with zero LLM latency."""
    role = _ROLE_INTRO[cfg.language][cfg.interviewer_role]
    if cfg.language == "zh":
        warm = {"friendly": "你好，欢迎！别紧张，就当是聊聊天。", "neutral": "你好。", "pressure": "你好，我们直接开始。"}[cfg.persona]
        return (
            f"{warm}我是{role}，今天这场面试大概{cfg.duration_min}分钟。"
            f"先请你简单做个自我介绍，重点讲讲和{cfg.job_title}相关的经历？"
        )
    warm = {"friendly": "Hi, welcome! Relax, think of this as a conversation.", "neutral": "Hello.", "pressure": "Hello. Let's get straight into it."}[cfg.persona]
    return (
        f"{warm} I'm {role}, and this interview will take about {cfg.duration_min} minutes. "
        f"Could you start by briefly introducing yourself, focusing on what's relevant to the {cfg.job_title} role?"
    )


async def build_plan(llm: LLM, cfg: InterviewConfig, profile: CandidateProfile | None) -> InterviewPlan:
    try:
        raw = await llm.structured(prompts.plan_messages(cfg, profile), InterviewPlan, temperature=0.6)
    except Exception as e:  # noqa: BLE001 - interview must still be able to start
        log.warning("Plan generation failed, using fallback: %s", e)
        raw = InterviewPlan(stages=[])
    return normalize(raw, cfg)
