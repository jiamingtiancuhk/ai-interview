import { useCallback, useEffect, useRef, useState } from 'react'
import { api, interviewSocket, type Language, type Message, type ServerEvent, type Snapshot } from '../api'
import { STAGE_LABEL, fmtTime } from '../labels'
import { navigate } from '../router'
import { Speaker } from '../voice/speaker'
import { useMic } from '../voice/useMic'

type Bubble = { role: Message['role']; content: string }
type Mode = 'voice' | 'text'

// Silence after the last speech segment before the answer is submitted.
// Long enough for a thinking pause, short enough to feel conversational.
const COMMIT_MS = 2500

function StageBar({ snap, elapsed }: { snap: Snapshot; elapsed: number }) {
  const over = elapsed > snap.duration_s
  return (
    <div className="flex flex-wrap items-center gap-2">
      {snap.stages.map((s, i) => (
        <span
          key={i}
          className={`rounded-full px-3 py-1 text-xs ${
            i === snap.stage_index && !snap.finished
              ? 'bg-zinc-900 text-white dark:bg-white dark:text-zinc-900'
              : i < snap.stage_index || snap.finished
                ? 'bg-zinc-200 text-zinc-500 dark:bg-zinc-800'
                : 'border border-zinc-300 text-zinc-500 dark:border-zinc-700'
          }`}
        >
          {STAGE_LABEL[s.kind]}
        </span>
      ))}
      <span className={`ml-auto font-mono text-sm tabular-nums ${over ? 'text-red-600' : 'text-zinc-500'}`}>
        {fmtTime(elapsed)} / {fmtTime(snap.duration_s)}
      </span>
    </div>
  )
}

function MicIndicator({ listening, speaking, transcribing }: { listening: boolean; speaking: boolean; transcribing: boolean }) {
  const label = speaking ? '正在听…' : transcribing ? '识别中…' : listening ? '轮到你了，直接开口回答' : '麦克风已暂停'
  return (
    <div className="flex items-center gap-2 text-sm text-zinc-500">
      <span className="relative flex h-3 w-3">
        {speaking && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75" />}
        <span className={`relative inline-flex h-3 w-3 rounded-full ${listening ? 'bg-red-500' : 'bg-zinc-300 dark:bg-zinc-700'}`} />
      </span>
      {label}
    </div>
  )
}

export default function Interview({ id }: { id: string }) {
  const [snap, setSnap] = useState<Snapshot | null>(null)
  const [lang, setLang] = useState<Language | null>(null)
  const [mode, setMode] = useState<Mode>('voice')
  const [bubbles, setBubbles] = useState<Bubble[]>([])
  const [draft, setDraft] = useState('')
  const [streaming, setStreaming] = useState('')
  const [thinking, setThinking] = useState(false)
  const [interviewerSpeaking, setInterviewerSpeaking] = useState(false)
  const [finished, setFinished] = useState(false)
  const [error, setError] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const [inflight, setInflight] = useState(0)
  const [commitAt, setCommitAt] = useState<number | null>(null)

  const ws = useRef<WebSocket | null>(null)
  const speaker = useRef<Speaker | null>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const clockBase = useRef<{ server: number; local: number } | null>(null)
  const draftRef = useRef('')
  draftRef.current = draft
  const modeRef = useRef(mode)
  modeRef.current = mode
  const finishedRef = useRef(false)
  finishedRef.current = finished
  const editedByHand = useRef(false)
  const langRef = useRef<Language | null>(null)
  langRef.current = lang

  const busy = thinking || streaming !== '' || interviewerSpeaking
  const myTurn = !busy && !finished && bubbles.at(-1)?.role === 'interviewer'
  const myTurnRef = useRef(myTurn)
  myTurnRef.current = myTurn

  const mic = useMic({
    onSegment: (audio) => {
      if (!myTurnRef.current || ws.current?.readyState !== WebSocket.OPEN) return
      setInflight((n) => n + 1)
      ws.current.send(audio.buffer as ArrayBuffer)
    },
    onSpeechStart: () => setCommitAt(null),
  })
  const micRef = useRef(mic)
  micRef.current = mic

  const submit = useCallback((text: string) => {
    const t = text.trim()
    if (!t || !myTurnRef.current) return
    setBubbles((b) => [...b, { role: 'candidate', content: t }])
    setDraft('')
    setCommitAt(null)
    setError('')
    editedByHand.current = false
    micRef.current.pause()
    ws.current?.send(JSON.stringify({ type: 'answer', text: t }))
  }, [])

  // --- socket ---------------------------------------------------------------
  useEffect(() => {
    let cancelled = false
    api.getInterview(id).then((d) => {
      if (cancelled) return
      setLang(d.config.language)
      speaker.current = new Speaker(d.config.language)
    })
    api.health().then((h) => {
      if (!cancelled && h.asr.state !== 'ready') setMode('text')
    })
    const sock = interviewSocket(id)
    ws.current = sock
    sock.binaryType = 'arraybuffer'
    sock.onopen = () => sock.send(JSON.stringify({ type: 'start' }))
    sock.onclose = () => {
      if (!cancelled) setError((e) => e || '连接已断开，刷新页面可以从断点继续。')
    }
    sock.onmessage = (ev) => {
      const msg: ServerEvent = JSON.parse(ev.data)
      const sp = speaker.current
      switch (msg.type) {
        case 'state':
          setSnap(msg)
          clockBase.current = { server: msg.elapsed_s, local: Date.now() }
          if (msg.finished) setFinished(true)
          break
        case 'history':
          setBubbles(msg.messages.map((m) => ({ role: m.role, content: m.content })))
          break
        case 'thinking':
          setThinking(true)
          break
        case 'interviewer_delta':
          setThinking(false)
          setStreaming((s) => s + msg.text)
          if (sp && modeRef.current === 'voice') {
            sp.feed(msg.text)
            setInterviewerSpeaking(sp.speaking)
          }
          break
        case 'interviewer_done':
          setStreaming('')
          setBubbles((b) => [...b, { role: 'interviewer', content: msg.text }])
          if (sp && modeRef.current === 'voice') sp.flush()
          break
        case 'transcript_segment':
          setInflight((n) => Math.max(0, n - 1))
          if (msg.text) {
            setDraft((d) => (d ? d + (langRef.current === 'en' ? ' ' : '') : '') + msg.text)
            if (!editedByHand.current) setCommitAt(Date.now() + COMMIT_MS)
          }
          break
        case 'finished':
          setFinished(true)
          setThinking(false)
          micRef.current.pause()
          break
        case 'error':
          setThinking(false)
          setError(msg.message)
          break
      }
    }
    return () => {
      cancelled = true
      sock.close()
      speaker.current?.cancel()
    }
  }, [id])

  // Interviewer audio lifecycle -> microphone.
  useEffect(() => {
    const sp = speaker.current
    if (!sp) return
    sp.onStart = () => setInterviewerSpeaking(true)
    sp.onIdle = () => setInterviewerSpeaking(false)
  }, [lang])

  useEffect(() => {
    if (mode === 'voice' && myTurn) mic.start()
    else if (!myTurn || mode === 'text') mic.pause()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, myTurn])

  // Auto-submit after a quiet period, once all segments are transcribed.
  useEffect(() => {
    if (commitAt === null || inflight > 0 || mic.userSpeaking) return
    const t = setTimeout(() => submit(draftRef.current), Math.max(0, commitAt - Date.now()))
    return () => clearTimeout(t)
  }, [commitAt, inflight, mic.userSpeaking, submit])

  // --- clock & scroll ---------------------------------------------------------
  useEffect(() => {
    const t = setInterval(() => {
      const base = clockBase.current
      if (base && !finishedRef.current) setElapsed(base.server + (Date.now() - base.local) / 1000)
    }, 500)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    // Braces matter: scrollIntoView returns a Promise in recent Chromium, and
    // React treats a non-function return value as a broken cleanup.
    bottom.current?.scrollIntoView({ behavior: 'smooth' })
  }, [bubbles, streaming, thinking, draft])

  function switchMode(m: Mode) {
    setMode(m)
    if (m === 'text') {
      speaker.current?.cancel()
      setInterviewerSpeaking(false)
    }
  }

  function end() {
    if (!confirm('确定提前结束面试吗？')) return
    speaker.current?.cancel()
    ws.current?.send(JSON.stringify({ type: 'end' }))
  }

  const lastInterviewer = [...bubbles].reverse().find((b) => b.role === 'interviewer')

  return (
    <div className="mx-auto flex h-dvh max-w-3xl flex-col px-4">
      <div className="flex items-center gap-4 border-b border-zinc-200 py-4 dark:border-zinc-800">
        <div className="flex-1">{snap && <StageBar snap={snap} elapsed={elapsed} />}</div>
        <div className="inline-flex rounded-lg bg-zinc-100 p-0.5 text-xs dark:bg-zinc-800">
          {(['voice', 'text'] as const).map((m) => (
            <button
              key={m}
              onClick={() => switchMode(m)}
              className={`rounded-md px-2.5 py-1 ${mode === m ? 'bg-white shadow-sm dark:bg-zinc-600' : 'text-zinc-500'}`}
            >
              {m === 'voice' ? '语音' : '文字'}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto py-6">
        {bubbles.map((b, i) => (
          <div key={i} className={b.role === 'candidate' ? 'flex justify-end' : ''}>
            <div
              className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-3 leading-relaxed ${
                b.role === 'candidate' ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900' : 'bg-zinc-100 dark:bg-zinc-800'
              }`}
            >
              {b.content}
            </div>
          </div>
        ))}
        {streaming && <div className="max-w-[85%] rounded-2xl bg-zinc-100 px-4 py-3 leading-relaxed dark:bg-zinc-800">{streaming}</div>}
        {thinking && <div className="text-sm text-zinc-500">面试官正在思考…</div>}
        {error && <div className="text-sm text-red-600">{error}</div>}
        {mic.state === 'error' && <div className="text-sm text-red-600">麦克风不可用：{mic.error}。可以切换到文字模式。</div>}
        {finished && (
          <div className="rounded-xl border border-zinc-200 p-4 text-center dark:border-zinc-800">
            <p className="mb-3">面试结束。</p>
            <button onClick={() => navigate(`/review/${id}`)} className="rounded-lg bg-zinc-900 px-4 py-2 text-white dark:bg-white dark:text-zinc-900">
              查看复盘
            </button>
          </div>
        )}
        <div ref={bottom} />
      </div>

      {!finished && (
        <div className="space-y-2 border-t border-zinc-200 py-4 dark:border-zinc-800">
          {mode === 'voice' && (
            <div className="flex items-center justify-between">
              <MicIndicator listening={mic.listening} speaking={mic.userSpeaking} transcribing={inflight > 0} />
              {interviewerSpeaking && (
                <button onClick={() => { speaker.current?.cancel(); setInterviewerSpeaking(false) }} className="text-xs text-zinc-500 underline">
                  跳过朗读
                </button>
              )}
            </div>
          )}
          <textarea
            value={draft}
            onChange={(e) => {
              editedByHand.current = true
              setCommitAt(null)
              setDraft(e.target.value)
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                submit(draft)
              }
            }}
            rows={3}
            placeholder={
              !myTurn ? '等面试官说完…' : mode === 'voice' ? '你说的话会出现在这里，停顿约 2 秒后自动发送；也可以直接修改' : '输入你的回答，Enter 发送，Shift+Enter 换行'
            }
            disabled={!myTurn}
            className="input resize-none"
          />
          {commitAt !== null && inflight === 0 && !mic.userSpeaking && (
            <div className="h-0.5 overflow-hidden rounded bg-zinc-100 dark:bg-zinc-800">
              <div key={commitAt} className="h-full bg-zinc-900 dark:bg-zinc-200" style={{ animation: `shrink ${COMMIT_MS}ms linear forwards` }} />
            </div>
          )}
          <div className="flex items-center gap-3">
            <button onClick={end} className="text-sm text-zinc-500 hover:text-red-600">
              结束面试
            </button>
            {lastInterviewer && mode === 'voice' && !busy && (
              <button onClick={() => speaker.current?.replay(lastInterviewer.content)} className="text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-white">
                再听一遍
              </button>
            )}
            <div className="flex-1" />
            {draft && (
              <button onClick={() => { setDraft(''); setCommitAt(null); editedByHand.current = false }} className="text-sm text-zinc-500">
                清空
              </button>
            )}
            <button
              onClick={() => submit(draft)}
              disabled={!myTurn || !draft.trim() || inflight > 0}
              className="rounded-lg bg-zinc-900 px-5 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-white dark:text-zinc-900"
            >
              {mode === 'voice' ? '我说完了' : '发送'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
