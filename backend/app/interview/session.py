"""One live interview: owns plan, state and transcript, drives each turn.

A turn is: evaluate the candidate's answer (structured LLM call) ->
policy.decide (pure code) -> stream the interviewer's reply (LLM stream).
"""

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from pydantic import BaseModel

from .. import config
from ..llm import LLM
from . import policy, prompts
from .models import (
    Action,
    AnswerType,
    CandidateProfile,
    Evaluation,
    InterviewConfig,
    InterviewPlan,
    InterviewState,
    Message,
    Scores,
)

log = logging.getLogger(__name__)


class TurnRecord(BaseModel):
    stage_index: int
    topic_index: int
    question: str
    answer: str
    evaluation: Evaluation
    action: Action
    eval_latency_s: float


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

    def _chat_history(self) -> list[dict]:
        role = {"interviewer": "assistant", "candidate": "user"}
        return [{"role": role[m.role], "content": m.content} for m in self.messages]

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
        msgs = [{"role": "system", "content": prompts.interviewer_system(self.cfg, self.plan, self.profile)}]
        msgs += self._chat_history()
        msgs.append({"role": "system", "content": prompts.directive(action, self.stage, self.topic, probe_angle)})
        parts: list[str] = []
        async for piece in llm.stream(msgs, temperature=0.7):
            parts.append(piece)
            yield piece
        self._add("interviewer", "".join(parts).strip())

    # -- public API ---------------------------------------------------------
    def open(self, llm: LLM) -> AsyncIterator[str]:
        self.started_at = time.time()
        return self._speak(llm, Action.open)

    async def evaluate(self, llm: LLM, answer: str) -> tuple[Evaluation, float]:
        msgs = prompts.evaluation_messages(self.cfg, self.stage, self.topic, self._topic_exchanges(answer))
        t0 = time.perf_counter()
        try:
            ev = await llm.structured(msgs, Evaluation)
        except Exception as e:  # noqa: BLE001 - keep the conversation going
            log.error("Evaluation failed: %s", e)
            ev = Evaluation(
                answer_type=AnswerType.answer,
                scores=Scores(relevance=3, depth=3, evidence=3, clarity=3, structure=3),
                strengths=[],
                gaps=["(evaluation unavailable)"],
                vague_claims=[],
                should_probe=False,
                probe_angle="",
                topic_exhausted=True,
            )
        return ev, time.perf_counter() - t0

    async def answer(self, llm: LLM, text: str) -> tuple[TurnRecord, AsyncIterator[str]]:
        """Record the candidate's answer, decide, and return the reply stream."""
        if self.state.finished:
            raise RuntimeError("Interview already finished")
        question = self._last_question()
        ev, latency = await self.evaluate(llm, text)
        self._add("candidate", text)
        prev = self.state
        decision = policy.decide(
            self.plan,
            self.state,
            ev,
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
            evaluation=ev,
            action=decision.action,
            eval_latency_s=round(latency, 2),
        )
        self.turns.append(record)
        log.info(
            "turn stage=%d topic=%d type=%s probe=%s -> %s",
            prev.stage_index, prev.topic_index, ev.answer_type, ev.should_probe, decision.action,
        )
        return record, self._speak(llm, decision.action, ev.probe_angle)

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
        return s

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
