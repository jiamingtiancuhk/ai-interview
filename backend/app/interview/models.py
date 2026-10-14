from enum import StrEnum

from pydantic import BaseModel, Field


class Language(StrEnum):
    zh = "zh"
    en = "en"


class Persona(StrEnum):
    friendly = "friendly"
    neutral = "neutral"
    pressure = "pressure"


class InterviewerRole(StrEnum):
    hr = "hr"
    tech_lead = "tech_lead"
    hiring_manager = "hiring_manager"


class StageKind(StrEnum):
    intro = "intro"
    resume_deep_dive = "resume_deep_dive"
    technical = "technical"
    behavioral = "behavioral"
    candidate_questions = "candidate_questions"


class InterviewConfig(BaseModel):
    job_title: str
    language: Language = Language.zh
    persona: Persona = Persona.neutral
    interviewer_role: InterviewerRole = InterviewerRole.tech_lead
    difficulty: str = "intermediate"  # junior | intermediate | senior
    duration_min: int = Field(30, ge=10, le=90)
    job_description: str = ""
    resume_text: str = ""


# ---------------------------------------------------------------------------
# LLM structured outputs. Keep field descriptions concrete: Ollama passes the
# JSON schema to the model, so they double as instructions.
# ---------------------------------------------------------------------------
class Project(BaseModel):
    name: str
    summary: str = Field(description="One sentence: what it was and the candidate's role")
    claims: list[str] = Field(description="Specific claims worth verifying, e.g. metrics or technologies")


class CandidateProfile(BaseModel):
    seniority_guess: str
    key_skills: list[str]
    projects: list[Project] = Field(description="Up to 4 most relevant projects/experiences")
    jd_requirements: list[str] = Field(description="Core requirements from the JD; empty if no JD")
    gaps: list[str] = Field(description="JD requirements the resume does not clearly evidence")


class Topic(BaseModel):
    title: str
    rationale: str = Field(description="Why this topic matters for this candidate and role")
    opening_question: str = Field(description="The first question to ask, phrased for speaking aloud")


class Stage(BaseModel):
    kind: StageKind
    goal: str
    minutes: int = Field(description="Time budget for this stage in minutes")
    topics: list[Topic]


class InterviewPlan(BaseModel):
    stages: list[Stage]


class AnswerType(StrEnum):
    answer = "answer"
    clarification_request = "clarification_request"
    dont_know = "dont_know"
    off_topic = "off_topic"
    candidate_question = "candidate_question"


class Routing(BaseModel):
    """Fast, small judgement that decides where the conversation goes next.

    Kept tiny on purpose: it sits on the critical path between the candidate
    finishing and the interviewer starting to speak.
    """

    answer_type: AnswerType
    needs_follow_up: bool = Field(
        description="True if the answer is vague, generic, lacks the candidate's own actions, numbers or "
        "trade-offs, or opens a thread worth digging into"
    )
    probe_angle: str = Field(description="If needs_follow_up: the single follow-up angle in under 20 words. Else empty")


class Scores(BaseModel):
    relevance: int = Field(ge=1, le=5)
    depth: int = Field(ge=1, le=5)
    evidence: int = Field(ge=1, le=5, description="Concrete examples, numbers, own contribution")
    clarity: int = Field(ge=1, le=5)
    structure: int = Field(ge=1, le=5, description="Logical flow, e.g. STAR for behavioral")


class Assessment(BaseModel):
    """Detailed scoring for the review. Computed off the critical path."""

    scores: Scores
    strengths: list[str]
    gaps: list[str] = Field(description="What is missing, wrong, or unconvincing")
    vague_claims: list[str] = Field(description="Claims stated without support that a real interviewer would press on")
    better_answer_hint: str = Field(description="One or two sentences: what a strong answer would have included")


# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------
class Action(StrEnum):
    open = "open"
    follow_up = "follow_up"
    clarify = "clarify"
    next_topic = "next_topic"
    next_stage = "next_stage"
    answer_candidate = "answer_candidate"
    wrap_up = "wrap_up"


class Message(BaseModel):
    role: str  # "interviewer" | "candidate"
    content: str
    stage_index: int
    topic_index: int
    elapsed_s: float


class InterviewState(BaseModel):
    stage_index: int = 0
    topic_index: int = 0
    follow_ups: int = 0
    stage_started_s: float = 0.0
    finished: bool = False
