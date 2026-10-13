import { useEffect, useRef, useState } from 'react'
import { interviewSocket, type Message, type ServerEvent, type Snapshot } from '../api'
import { STAGE_LABEL, fmtTime } from '../labels'
import { navigate } from '../router'

type Bubble = { role: Message['role']; content: string }

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

export default function Interview({ id }: { id: string }) {
  const [snap, setSnap] = useState<Snapshot | null>(null)
  const [bubbles, setBubbles] = useState<Bubble[]>([])
  const [draft, setDraft] = useState('')
  const [streaming, setStreaming] = useState('')
  const [thinking, setThinking] = useState(false)
  const [finished, setFinished] = useState(false)
  const [error, setError] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const ws = useRef<WebSocket | null>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const clockBase = useRef<{ server: number; local: number } | null>(null)

  useEffect(() => {
    const sock = interviewSocket(id)
    ws.current = sock
    sock.onopen = () => sock.send(JSON.stringify({ type: 'start' }))
    sock.onclose = () => setError((e) => e || '连接已断开，刷新页面可以从断点继续。')
    sock.onmessage = (ev) => {
      const msg: ServerEvent = JSON.parse(ev.data)
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
          break
        case 'interviewer_done':
          setStreaming('')
          setBubbles((b) => [...b, { role: 'interviewer', content: msg.text }])
          break
        case 'finished':
          setFinished(true)
          setThinking(false)
          break
        case 'error':
          setThinking(false)
          setError(msg.message)
          break
      }
    }
    return () => sock.close()
  }, [id])

  useEffect(() => {
    const t = setInterval(() => {
      const base = clockBase.current
      if (base && !finished) setElapsed(base.server + (Date.now() - base.local) / 1000)
    }, 500)
    return () => clearInterval(t)
  }, [finished])

  useEffect(() => bottom.current?.scrollIntoView({ behavior: 'smooth' }), [bubbles, streaming, thinking])

  const busy = thinking || streaming !== ''
  const myTurn = !busy && !finished && bubbles.at(-1)?.role === 'interviewer'

  function send() {
    const text = draft.trim()
    if (!text || !myTurn) return
    setBubbles((b) => [...b, { role: 'candidate', content: text }])
    setDraft('')
    setError('')
    ws.current?.send(JSON.stringify({ type: 'answer', text }))
  }

  function end() {
    if (!confirm('确定提前结束面试吗？')) return
    ws.current?.send(JSON.stringify({ type: 'end' }))
  }

  return (
    <div className="mx-auto flex h-dvh max-w-3xl flex-col px-4">
      <div className="space-y-3 border-b border-zinc-200 py-4 dark:border-zinc-800">
        {snap && <StageBar snap={snap} elapsed={finished ? (snap.elapsed_s ?? elapsed) : elapsed} />}
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto py-6">
        {bubbles.map((b, i) => (
          <div key={i} className={b.role === 'candidate' ? 'flex justify-end' : ''}>
            <div
              className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-3 leading-relaxed ${
                b.role === 'candidate'
                  ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                  : 'bg-zinc-100 dark:bg-zinc-800'
              }`}
            >
              {b.content}
            </div>
          </div>
        ))}
        {streaming && <div className="max-w-[85%] rounded-2xl bg-zinc-100 px-4 py-3 leading-relaxed dark:bg-zinc-800">{streaming}</div>}
        {thinking && <div className="text-sm text-zinc-500">面试官正在思考…</div>}
        {error && <div className="text-sm text-red-600">{error}</div>}
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
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                send()
              }
            }}
            rows={3}
            placeholder={myTurn ? '输入你的回答，Enter 发送，Shift+Enter 换行' : '等面试官说完…'}
            disabled={!myTurn}
            className="input resize-none"
          />
          <div className="flex justify-between">
            <button onClick={end} className="text-sm text-zinc-500 hover:text-red-600">
              结束面试
            </button>
            <button
              onClick={send}
              disabled={!myTurn || !draft.trim()}
              className="rounded-lg bg-zinc-900 px-5 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-white dark:text-zinc-900"
            >
              发送
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
