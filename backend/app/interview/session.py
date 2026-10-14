"""One live interview: owns plan, state and transcript, drives each turn.

Critical path of a turn (candidate stops talking -> interviewer speaks):
    route (tiny structured LLM call) -> policy.decide (pure code)
    -> stream the interviewer's reply, cut after the first question.
Off the critical path, while the candidate is answering the next question:
    assess (detailed scoring for the review).
"""

import asyncio
import json
import logging
import re
import time
import uuid
from difflib import SequenceMatcher
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from pydantic import BaseModel

from .. import config
from ..llm import LLM
from . import planner, policy, prompts
from .models import (
    Action,
    AnswerType,
    Assessment,
    CandidateProfile,
    InterviewConfig,
    InterviewPlan,
    InterviewState,
    Message,
    Report,
    Routing,
    StageFeedback,
    StageKind,
)

log = logging.getLogger(__name__)

_SENTENCE_END = re.compile(r"[。！？!?；;\n]|\.(?=\s)")
_SPEAKER_PREFIX = re.compile(r"^\s*[\"“]?\s*(interviewer|面试官)\s*[:：]\s*", re.IGNORECASE)
_NON_WORD = re.compile(r"[\W_]+")
# Actions whose reply must end at the interviewer's (single) question.
_ENDS_WITH_QUESTION = {Action.open, Action.follow_up, Action.clarify, Action.next_topic, Action.next_stage}
_MAX_SENTENCES = 4


def _norm(text: str) -> str:
    return _NON_WORD.sub("", text).lower()


def _is_echo(sentence: str, recent: list[str]) -> bool:
    """True if the sentence just repeats something already said.

    Small models like to open by restating the previous question; spoken
    aloud that sounds broken, so such sentences are dropped.
    """
    s = _norm(sentence)
    if len(s) < 6:
        return False
    return any(s in r or SequenceMatcher(None, s, r).ratio() > 0.85 for r in recent)


def _tidy_report(report: Report, kinds: list[StageKind]) -> Report:
    """Enforce one entry per stage (in interview order) and no duplicate advice.

    Small models sometimes write one stage entry per answer; merge those by
    averaging the score and keeping the first comment.
    """
    merged: dict[StageKind, list] = {}
    for st in report.stages:
        merged.setdefault(st.kind, []).append(st)
    stages = [
        StageFeedback(kind=k, score=round(sum(x.score for x in merged[k]) / len(merged[k])), comment=merged[k][0].comment)
        for k in kinds
        if k in merged
    ]
    seen: set[str] = set()
    improvements = []
    for im in report.improvements:
        if _norm(im.how_to_practice) not in seen:
            seen.add(_norm(im.how_to_practice))
            improvements.append(im)
    return report.model_copy(update={"stages": stages, "improvements": improvements})


class TurnRecord(BaseModel):
    stage_index: int
    topic_index: int
    question: str
    answer: str
    routing: Routing
    action: Action
    route_latency_s: float
    # Q/A thread on this topic up to this answer; input for the assessment.
    context: list[tuple[str, str]]
    assessment: Assessment | None = None

    @property
    def scorable(self) -> bool:
        """Asking the interviewer something is not an answer to be graded."""
        return self.routing.answer_type not in (AnswerType.candidate_question, AnswerType.clarification_request)


@dataclass
class InterviewSession:
    cfg: InterviewConfig
    plan: InterviewPlan
    profile: CandidateProfile | None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: InterviewState = field(default_factory=InterviewState)
    messages: list[Message] = field(default_factory=list)
    turns: list[TurnRecord] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    # Wall-clock offset so a resumed session keeps its elapsed time.
    paused_elapsed_s: float = 0.0
    report: Report | None = None
    _assess_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _planning: asyncio.Task | None = field(default=None, repr=False)

    # -- helpers ------------------------------------------------------------
    def elapsed_s(self) -> float:
        return self.paused_elapsed_s + (time.time() - self.started_at)

    @property
    def stage(self):
        return self.plan.stages[self.state.stage_index]

    @property
    def topic(self):
        return self.stage.topics[self.state.topic_index]

    def _topic_exchanges(self, answer: str) -> list[tuple[str, str]]:
        """Q/A pairs so far on the current topic, ending with the new answer."""
        pairs: list[tuple[str, str]] = []
        q = None
        for m in self.messages:
            if (m.stage_index, m.topic_index) != (self.state.stage_index, self.state.topic_index):
                continue
            if m.role == "interviewer":
                q = m.content
            elif q is not None:
                pairs.append((q, m.content))
                q = None
        pairs.append((q or self._last_question(), answer))
        return pairs

    def _last_question(self) -> str:
        for m in reversed(self.messages):
            if m.role == "interviewer":
                return m.content
        return ""

    def _add(self, role: str, content: str) -> None:
        self.messages.append(
            Message(
                role=role,
                content=content,
                stage_index=self.state.stage_index,
                topic_index=self.state.topic_index,
                elapsed_s=round(self.elapsed_s(), 1),
            )
        )

    async def _speak(self, llm: LLM, action: Action, probe_angle: str = "") -> AsyncIterator[str]:
        """Stream the interviewer's reply sentence by sentence, with guardrails:
        strip a leading "Interviewer:" label, drop sentences that echo earlier
        messages, and stop after the first question so exactly one is asked
        (which also aborts generation early and saves time)."""
        msgs = prompts.speaker_messages(
            self.cfg, self.profile, [(m.role, m.content) for m in self.messages],
            action, self.stage, self.topic, probe_angle,
        )
        recent = [_norm(m.content) for m in self.messages[-3:]]
        joiner = "" if self.cfg.language == "zh" else " "
        said: list[str] = []
        dropped: list[str] = []
        buf = ""
        stream = llm.stream(msgs, temperature=0.7)

        def accept(sentence: str) -> str | None:
            sentence = _SPEAKER_PREFIX.sub("", sentence).strip() if not said else sentence.strip()
            if not sentence:
                return None
            if _is_echo(sentence, recent):
                dropped.append(sentence)
                return None
            said.append(sentence)
            return (joiner if len(said) > 1 else "") + sentence

        def done() -> bool:
            last = said[-1] if said else ""
            asked = action in _ENDS_WITH_QUESTION and last.endswith(("?", "？"))
            return asked or len(said) >= _MAX_SENTENCES

        try:
            async for piece in stream:
                buf += piece
                while (m := _SENTENCE_END.search(buf)) is not None:
                    sentence, buf = buf[: m.end()], buf[m.end():]
                    if (out := accept(sentence)) is not None:
                        yield out
                        if done():
                            return
            if (out := accept(buf)) is not None:
                yield out
            elif not said and dropped:
                # Everything was an echo (e.g. a near-verbatim rephrase): better than silence.
                said.append(dropped[-1])
                yield dropped[-1]
            if (bridge := self._return_to_question(action, said)) is not None:
                said.append(bridge)
                yield joiner + bridge
        finally:
            await stream.aclose()
            self._add("interviewer", joiner.join(said).strip())

    def _return_to_question(self, action: Action, said: list[str]) -> str | None:
        """After answering a candidate's question mid-interview, make sure the
        interviewer's own open question is not lost."""
        if action != Action.answer_candidate or self.stage.kind == StageKind.candidate_questions:
            return None
        if said and said[-1].endswith(("?", "？")):
            return None
        last_q = next((m.content for m in reversed(self.messages) if m.role == "interviewer"), "")
        sentences = [x for x in re.split(r"(?<=[。！？!?])\s*", last_q) if x.endswith(("?", "？"))]
        if not sentences:
            return None
        lead = "那我们回到刚才的问题：" if self.cfg.language == "zh" else "Back to my question: "
        return lead + sentences[-1]

    # -- public API ---------------------------------------------------------
    def start_planning(self, llm: LLM) -> None:
        """Read the resume/JD and plan the interview in the background.

        The interview starts immediately on a skeleton plan; the warm-up
        (self-introduction) needs no personalised plan, and takes longer than
        planning does, so the candidate never waits for it.
        """

        async def run() -> None:
            t0 = time.perf_counter()
            try:
                profile = await planner.build_profile(llm, self.cfg)
            except Exception as e:  # noqa: BLE001 - fall back to a generic plan
                log.warning("Profile extraction failed: %s", e)
                profile = None
            plan = await planner.build_plan(llm, self.cfg, profile)
            self.profile = profile
            # Stages already reached keep their topics; only the future changes.
            for i in range(self.state.stage_index + 1, len(plan.stages)):
                self.plan.stages[i] = plan.stages[i]
            log.info("plan ready in %.1fs", time.perf_counter() - t0)

        self._planning = asyncio.create_task(run())

    async def wait_for_plan(self) -> None:
        if self._planning is not None:
            await asyncio.shield(self._planning)

    async def open(self, llm: LLM) -> AsyncIterator[str]:
        self.started_at = time.time()
        line = planner.opening_line(self.cfg)
        self._add("interviewer", line)
        yield line

    async def route(self, llm: LLM, exchanges: list[tuple[str, str]]) -> tuple[Routing, float]:
        msgs = prompts.routing_messages(self.cfg, self.stage, self.topic, exchanges)
        t0 = time.perf_counter()
        try:
            r = await llm.structured(msgs, Routing, temperature=0.0)
        except Exception as e:  # noqa: BLE001 - keep the conversation going
            log.error("Routing failed: %s", e)
            r = Routing(answer_type=AnswerType.answer, needs_follow_up=False, probe_angle="")
        return r, time.perf_counter() - t0

    async def answer(self, llm: LLM, text: str) -> tuple[TurnRecord, AsyncIterator[str]]:
        """Record the candidate's answer, decide, and return the reply stream."""
        if self.state.finished:
            raise RuntimeError("Interview already finished")
        await self.wait_for_plan()  # usually long done; the policy needs real topics
        question = self._last_question()
        exchanges = self._topic_exchanges(text)
        routing, latency = await self.route(llm, exchanges)
        self._add("candidate", text)
        prev = self.state
        decision = policy.decide(
            self.plan,
            self.state,
            routing,
            elapsed_s=self.elapsed_s(),
            total_budget_s=self.cfg.duration_min * 60,
            max_follow_ups=config.MAX_FOLLOW_UPS,
        )
        self.state = decision.state
        record = TurnRecord(
            stage_index=prev.stage_index,
            topic_index=prev.topic_index,
            question=question,
            answer=text,
            routing=routing,
            action=decision.action,
            route_latency_s=round(latency, 2),
            context=exchanges,
        )
        self.turns.append(record)
        log.info(
            "turn stage=%d topic=%d type=%s follow=%s -> %s (route %.2fs)",
            prev.stage_index, prev.topic_index, routing.answer_type, routing.needs_follow_up, decision.action, latency,
        )
        return record, self._speak(llm, decision.action, routing.probe_angle)

    async def assess_pending(self, llm: LLM) -> int:
        """Score answers that have not been assessed yet. Returns how many."""
        async with self._assess_lock:
            done = 0
            for t in self.turns:
                if t.assessment is not None or not t.scorable:
                    continue
                stage = self.plan.stages[t.stage_index]
                msgs = prompts.assessment_messages(self.cfg, stage, stage.topics[t.topic_index], t.context)
                try:
                    t.assessment = await llm.structured(msgs, Assessment)
                    done += 1
                except Exception as e:  # noqa: BLE001 - retried on the next call
                    log.warning("Assessment failed: %s", e)
            return done

    def to_record(self) -> dict:
        return {
            "id": self.id,
            "config": self.cfg.model_dump_json(),
            "profile": self.profile.model_dump_json() if self.profile else None,
            "plan": self.plan.model_dump_json(),
            "state": self.state.model_dump_json(),
            "messages": "[" + ",".join(m.model_dump_json() for m in self.messages) + "]",
            "turns": "[" + ",".join(t.model_dump_json() for t in self.turns) + "]",
            "elapsed_s": self.elapsed_s(),
            "finished": int(self.state.finished),
            "report": self.report.model_dump_json() if self.report else None,
        }

    @classmethod
    def from_record(cls, row: dict) -> "InterviewSession":
        s = cls(
            cfg=InterviewConfig.model_validate_json(row["config"]),
            plan=InterviewPlan.model_validate_json(row["plan"]),
            profile=CandidateProfile.model_validate_json(row["profile"]) if row["profile"] else None,
            id=row["id"],
            state=InterviewState.model_validate_json(row["state"]),
            messages=[Message.model_validate(m) for m in json.loads(row["messages"])],
            turns=[TurnRecord.model_validate(t) for t in json.loads(row["turns"])],
        )
        s.paused_elapsed_s = row["elapsed_s"]
        if row.get("report"):
            s.report = Report.model_validate_json(row["report"])
        return s

    def asr_terms(self) -> list[str]:
        """Vocabulary hint for speech recognition: current question first."""
        from ..asr import vocabulary

        skills = " ".join(self.profile.key_skills) if self.profile else ""
        return vocabulary(self._last_question(), skills, self.cfg.resume_text, self.cfg.job_description)

    @property
    def assessment_pending(self) -> bool:
        return any(t.scorable and t.assessment is None for t in self.turns)

    @property
    def review_pending(self) -> bool:
        """Something is still being computed for the review page."""
        has_answers = any(t.scorable for t in self.turns)
        return self.assessment_pending or (self.state.finished and has_answers and self.report is None)

    async def build_report(self, llm: LLM) -> Report | None:
        """Debrief over all assessed answers; run once the interview is over."""
        scored = [t for t in self.turns if t.assessment is not None]
        if not scored:
            return None
        by_stage: dict[StageKind, list[TurnRecord]] = {}
        for t in scored:
            by_stage.setdefault(self.plan.stages[t.stage_index].kind, []).append(t)
        sections = []
        for kind, turns in by_stage.items():
            lines = [f"## Stage: {kind}"]
            for t in turns:
                a = t.assessment
                lines.append(
                    f"Q: {t.question}\nA: {t.answer[:800]}\n"
                    f"scores={a.scores.model_dump()} gaps={a.gaps} vague={a.vague_claims}"
                )
            sections.append("\n".join(lines))
        msgs = prompts.report_messages(self.cfg, "\n\n".join(sections), [str(k) for k in by_stage])
        report = await llm.structured(msgs, Report, temperature=0.3)
        self.report = _tidy_report(report, list(by_stage))
        return self.report

    def snapshot(self) -> dict:
        """Client-facing progress (no scores: the interview should feel real)."""
        return {
            "session_id": self.id,
            "stage_index": self.state.stage_index,
            "stage_kind": self.stage.kind,
            "topic_index": self.state.topic_index,
            "stages": [{"kind": s.kind, "minutes": s.minutes, "topics": len(s.topics)} for s in self.plan.stages],
            "elapsed_s": round(self.elapsed_s(), 1),
            "duration_s": self.cfg.duration_min * 60,
            "finished": self.state.finished,
        }
