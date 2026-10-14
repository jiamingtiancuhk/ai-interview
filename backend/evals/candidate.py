"""Simulated candidates with known ground truth.

The harness, not the LLM, decides what kind of answer each turn should be
(seeded per persona). The candidate model only acts it out. Every turn
therefore carries an `intended` label to score the interviewer against,
without needing an LLM judge.
"""

import random
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel

from app.interview.models import InterviewConfig
from app.llm import LLM


class Behavior(StrEnum):
    solid = "solid"
    vague = "vague"
    off_topic = "off_topic"
    clarify = "clarify"
    dont_know = "dont_know"
    candidate_question = "candidate_question"
    # Only in the Q&A stage: the candidate has nothing (more) to ask.
    no_more_questions = "no_more_questions"


# What the interviewer's routing should classify each behavior as.
EXPECTED_TYPE = {
    Behavior.solid: "answer",
    Behavior.vague: "answer",
    Behavior.off_topic: "off_topic",
    Behavior.clarify: "clarification_request",
    Behavior.dont_know: "dont_know",
    Behavior.candidate_question: "candidate_question",
    Behavior.no_more_questions: "answer",
}


@dataclass(frozen=True)
class Persona:
    name: str
    weights: dict[Behavior, float]


PERSONAS = {
    p.name: p
    for p in [
        Persona("strong", {Behavior.solid: 0.8, Behavior.clarify: 0.1, Behavior.candidate_question: 0.1}),
        Persona("vague", {Behavior.vague: 0.8, Behavior.solid: 0.1, Behavior.dont_know: 0.1}),
        Persona("mixed", {Behavior.solid: 0.45, Behavior.vague: 0.4, Behavior.dont_know: 0.15}),
        Persona("confused", {Behavior.clarify: 0.35, Behavior.off_topic: 0.3, Behavior.vague: 0.2, Behavior.solid: 0.15}),
        Persona("curious", {Behavior.candidate_question: 0.35, Behavior.solid: 0.4, Behavior.vague: 0.25}),
    ]
}


def schedule(persona: Persona, turns: int, seed: int) -> list[Behavior]:
    """Deterministic behavior sequence. The first answer (self-intro) is always
    a real answer so every interview gets past the warm-up the same way."""
    rng = random.Random(f"{persona.name}:{seed}")
    kinds, weights = zip(*persona.weights.items())
    first = Behavior.vague if persona.name == "vague" else Behavior.solid
    return [first] + rng.choices(kinds, weights=weights, k=turns - 1)


_INSTRUCTIONS = {
    Behavior.solid: (
        "Give a STRONG answer: 4-6 sentences, specific to your resume, say what YOU personally did (use 'I'), "
        "include concrete numbers, a trade-off you considered and why. Structured but spoken."
    ),
    Behavior.vague: (
        "Give a VAGUE, weak answer TO THIS QUESTION: 1-2 short sentences of generic statements about the topic, "
        "say 'we' instead of 'I', no numbers, no specifics, no trade-offs. Sound like you are avoiding details."
    ),
    Behavior.off_topic: (
        "Go OFF-TOPIC: do not answer the question at all; instead talk about something unrelated to it "
        "(e.g. an unrelated hobby or an unrelated side project). 2-3 sentences. Do NOT ask any question."
    ),
    Behavior.clarify: (
        "You do NOT understand the question. Ask the interviewer to explain or rephrase it. "
        "One sentence, a question, and do not attempt any answer."
    ),
    Behavior.dont_know: "Admit honestly that you do not know or have no experience with this. 1-2 sentences, no attempt to answer.",
    Behavior.no_more_questions: "Say you have no further questions and thank the interviewer. One or two sentences, no question.",
    Behavior.candidate_question: (
        "Do NOT answer. Instead ask the interviewer ONE question about the team, the role, the tech stack "
        "or the hiring process. One sentence."
    ),
}

_EXAMPLES = {
    Behavior.clarify: {
        "zh": "抱歉，我没太听懂这个问题，你是想问具体的实现细节，还是整体的设计思路？",
        "en": "Sorry, I'm not sure I follow. Do you mean the implementation details or the overall design?",
    },
    Behavior.candidate_question: {
        "zh": "我想先问一下，这个团队现在主要在做哪些项目？",
        "en": "Can I ask what the team is mainly working on right now?",
    },
}

_LANG = {"zh": "Simplified Chinese, natural spoken style", "en": "English, natural spoken style"}

_DEFINITIONS = {
    Behavior.solid: "a specific, substantive attempt to answer the interviewer's question",
    Behavior.vague: "an attempt to answer the question that is generic and lacks specifics, numbers or personal contribution",
    Behavior.off_topic: "talks about something unrelated, does not address the question, and asks no question",
    Behavior.clarify: "asks the interviewer to explain or rephrase THEIR question, without answering it",
    Behavior.dont_know: "says they do not know or lack experience, without really answering",
    Behavior.candidate_question: "asks the interviewer about the team, role, company or process instead of answering",
    Behavior.no_more_questions: "says they have no (further) questions, without asking anything",
}


async def _generate(llm: LLM, cfg: InterviewConfig, transcript: list[tuple[str, str]], behavior: Behavior) -> str:
    history = "\n".join(f"{'Interviewer' if r == 'interviewer' else 'You'}: {c}" for r, c in transcript[-8:])
    msgs = [
        {
            "role": "system",
            "content": (
                f"You are role-playing a job candidate interviewing for '{cfg.job_title}'. Your resume:\n{cfg.resume_text}\n\n"
                f"Speak {_LANG[cfg.language]}. Output ONLY your spoken words: no quotes, labels, markdown or stage directions."
            ),
        },
        {
            "role": "user",
            "content": (
                f"{history}\n\nINSTRUCTION FOR THIS REPLY: {_INSTRUCTIONS[behavior]}"
                + (f"\nExample of the style (use your own words, adapted to the question): {ex}"
                   if (ex := _EXAMPLES.get(behavior, {}).get(cfg.language)) else "")
                + "\n\nYour reply:"
            ),
        },
    ]
    parts = [p async for p in llm.stream(msgs, temperature=0.8)]
    return "".join(parts).strip().strip('"“”')


class _Check(BaseModel):
    matches: bool


async def verify(llm: LLM, question: str, reply: str, behavior: Behavior) -> bool:
    """Does the simulated reply really show the intended behavior?"""
    msgs = [
        {"role": "system", "content": "You check the labels of an interview dataset. Answer strictly."},
        {
            "role": "user",
            "content": (
                f"Interviewer asked: {question}\nCandidate replied: {reply}\n\n"
                f"Is this reply {_DEFINITIONS[behavior]}? matches=true only if it clearly is."
            ),
        },
    ]
    return (await llm.structured(msgs, _Check, temperature=0.0)).matches


async def answer(
    llm: LLM, cfg: InterviewConfig, transcript: list[tuple[str, str]], behavior: Behavior, attempts: int = 3
) -> tuple[str, bool]:
    """Generate a reply showing `behavior`; regenerate if it does not.
    Returns the reply and whether it passed verification."""
    question = next((c for r, c in reversed(transcript) if r == "interviewer"), "")
    text = ""
    for _ in range(attempts):
        text = await _generate(llm, cfg, transcript, behavior)
        if await verify(llm, question, text, behavior):
            return text, True
    return text, False
