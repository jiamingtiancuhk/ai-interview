import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import asr, config
from .documents import extract_text
from .interview import planner
from .interview.models import InterviewConfig
from .interview.session import InterviewSession
from .llm import LLMError, OllamaLLM
from .store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

llm = OllamaLLM()
store = Store()
live: dict[str, InterviewSession] = {}
locks: dict[str, asyncio.Lock] = {}
assessing: dict[str, asyncio.Task] = {}


def assess_in_background(s: InterviewSession) -> None:
    """Score the latest answers while the candidate is busy answering the next question."""

    async def run():
        if await s.assess_pending(llm):
            store.save(s)
        if s.state.finished and s.report is None and not s.assessment_pending:
            try:
                await s.build_report(llm)
                store.save(s)
            except LLMError as e:
                log.warning("Report failed for %s: %s", s.id, e)

    task = asyncio.create_task(run())
    assessing[s.id] = task
    task.add_done_callback(lambda t: assessing.pop(s.id, None) if assessing.get(s.id) is t else None)


def preempt_assessment(s: InterviewSession) -> None:
    """The live conversation has priority over background scoring: Ollama
    serves one request at a time, so cancel it (unscored turns are retried)."""
    task = assessing.pop(s.id, None)
    if task and not task.done():
        task.cancel()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("LLM=%s @ %s, ASR=%s, DB=%s", config.LLM_MODEL, config.OLLAMA_URL, config.ASR_MODEL, config.DB_PATH)
    warm = asyncio.create_task(asr.warmup())
    yield
    warm.cancel()
    await llm.aclose()


app = FastAPI(title="AI Interview", lifespan=lifespan)


def get_session(session_id: str) -> InterviewSession:
    s = live.get(session_id) or store.load(session_id)
    if s is None:
        raise HTTPException(404, "Interview not found")
    live[session_id] = s
    return s


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    return {"llm": await llm.health(), "asr": asr.status}


@app.post("/api/documents/parse")
async def parse_document(file: UploadFile):
    try:
        return {"text": extract_text(file.filename or "", await file.read())}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Could not read document: {e}") from e


@app.post("/api/interviews")
async def create_interview(cfg: InterviewConfig):
    health = await llm.health()
    if not health["model_ready"]:
        raise HTTPException(503, f"LLM not ready: {health.get('error') or health['model'] + ' not installed'}")
    s = InterviewSession(cfg=cfg, plan=planner.skeleton_plan(cfg), profile=None)
    s.start_planning(llm)
    live[s.id] = s
    store.save(s)
    return s.snapshot()


@app.get("/api/interviews")
async def list_interviews():
    out = []
    for r in store.list():
        cfg = json.loads(r.pop("config"))
        out.append({**r, "job_title": cfg["job_title"], "language": cfg["language"],
                    "interviewer_role": cfg["interviewer_role"], "persona": cfg["persona"]})
    return out


@app.get("/api/interviews/{session_id}")
async def get_interview(session_id: str):
    s = get_session(session_id)
    data = {
        **s.snapshot(),
        "config": s.cfg.model_dump(exclude={"resume_text", "job_description"}),
        "messages": [m.model_dump() for m in s.messages],
    }
    # Assessments stay hidden until the interview is over, like a real one.
    if s.state.finished:
        if s.review_pending and s.id not in assessing:
            assess_in_background(s)
        data["assessing"] = s.review_pending
        data["report"] = s.report.model_dump() if s.report else None
        data["plan"] = s.plan.model_dump()
        data["profile"] = s.profile.model_dump() if s.profile else None
        data["turns"] = [t.model_dump() for t in s.turns]
    return data


# ---------------------------------------------------------------------------
# Live interview over WebSocket
#   client -> {"type": "start"} | {"type": "answer", "text": str} | {"type": "end"}
#             binary frame: one speech segment, 16 kHz mono float32 PCM
#   server -> state | history | thinking | interviewer_delta | interviewer_done
#             | transcript_segment | finished | error
# ---------------------------------------------------------------------------
async def stream_reply(ws: WebSocket, s: InterviewSession, chunks) -> None:
    text = []
    async for piece in chunks:
        text.append(piece)
        await ws.send_json({"type": "interviewer_delta", "text": piece})
    await ws.send_json({"type": "interviewer_done", "text": "".join(text).strip()})
    store.save(s)
    await ws.send_json({"type": "state", **s.snapshot()})
    if s.state.finished:
        await ws.send_json({"type": "finished"})
    assess_in_background(s)


@app.websocket("/api/interviews/{session_id}/ws")
async def interview_ws(ws: WebSocket, session_id: str):
    await ws.accept()
    try:
        s = get_session(session_id)
    except HTTPException:
        await ws.send_json({"type": "error", "message": "Interview not found"})
        await ws.close()
        return
    lock = locks.setdefault(session_id, asyncio.Lock())

    try:
        while True:
            frame = await ws.receive()
            if frame["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(frame.get("code", 1000))
            if frame.get("bytes") is not None:
                text, latency = await asr.transcribe_pcm(frame["bytes"], s.cfg.language, s.asr_terms())
                await ws.send_json({"type": "transcript_segment", "text": text, "latency_s": round(latency, 2)})
                continue
            msg = json.loads(frame["text"])
            kind = msg.get("type")
            async with lock:
                try:
                    await handle(ws, s, kind, msg)
                except LLMError as e:
                    log.error("LLM error in session %s: %s", session_id, e)
                    await ws.send_json({"type": "error", "message": str(e)})
                    store.save(s)
    except WebSocketDisconnect:
        store.save(s)


async def handle(ws: WebSocket, s: InterviewSession, kind: str, msg: dict) -> None:
    if kind == "start":
        await ws.send_json({"type": "state", **s.snapshot()})
        if s.messages:
            await ws.send_json({"type": "history", "messages": [m.model_dump() for m in s.messages]})
        else:
            await ws.send_json({"type": "thinking"})
            await stream_reply(ws, s, s.open(llm))
    elif kind == "answer":
        text = (msg.get("text") or "").strip()
        if not text or s.state.finished:
            return
        await ws.send_json({"type": "thinking"})
        preempt_assessment(s)
        _, chunks = await s.answer(llm, text)
        await stream_reply(ws, s, chunks)
    elif kind == "end":
        s.state = s.state.model_copy(update={"finished": True})
        store.save(s)
        await ws.send_json({"type": "finished"})
        assess_in_background(s)


# ---------------------------------------------------------------------------
# Frontend (production build)
# ---------------------------------------------------------------------------
if config.STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=config.STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        # Real files (VAD model, wasm, favicon) are served as-is; every other
        # path is a client-side route.
        file = (config.STATIC_DIR / path).resolve()
        if path and file.is_file() and file.is_relative_to(config.STATIC_DIR.resolve()):
            return FileResponse(file)
        return FileResponse(config.STATIC_DIR / "index.html")
