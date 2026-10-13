import { useEffect, useState } from 'react'
import { api, type InterviewDetail, type Scores } from '../api'
import { ACTION_LABEL, ROLE_LABEL, SCORE_LABEL, STAGE_LABEL, fmtTime } from '../labels'

function avg(scores: Scores[]): Scores | null {
  if (!scores.length) return null
  const keys = Object.keys(scores[0]) as (keyof Scores)[]
  return Object.fromEntries(keys.map((k) => [k, scores.reduce((a, s) => a + s[k], 0) / scores.length])) as unknown as Scores
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="w-10 text-zinc-500">{label}</span>
      <div className="h-2 flex-1 rounded-full bg-zinc-100 dark:bg-zinc-800">
        <div className="h-2 rounded-full bg-zinc-900 dark:bg-zinc-200" style={{ width: `${(value / 5) * 100}%` }} />
      </div>
      <span className="w-8 text-right font-mono tabular-nums">{value.toFixed(1)}</span>
    </div>
  )
}

function List({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  if (!items.length) return null
  return (
    <div>
      <div className={`text-xs font-medium ${tone}`}>{title}</div>
      <ul className="ml-4 list-disc text-sm text-zinc-700 dark:text-zinc-300">
        {items.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ul>
    </div>
  )
}

export default function Review({ id }: { id: string }) {
  const [d, setD] = useState<InterviewDetail | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getInterview(id).then(setD).catch((e) => setError(e.message))
  }, [id])

  if (error) return <p className="p-10 text-red-600">{error}</p>
  if (!d) return <p className="p-10 text-zinc-500">加载中…</p>
  if (!d.turns) return <p className="p-10 text-zinc-500">面试还没结束，结束后才能看复盘。</p>

  const answered = d.turns.filter((t) => t.evaluation.answer_type !== 'candidate_question')
  const overall = avg(answered.map((t) => t.evaluation.scores))

  return (
    <div className="mx-auto max-w-3xl space-y-8 px-4 py-10">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">{d.config.job_title} · 复盘</h1>
        <p className="text-sm text-zinc-500">
          {ROLE_LABEL[d.config.interviewer_role]} · 用时 {fmtTime(d.elapsed_s)} · 回答 {answered.length} 题
        </p>
      </header>

      {overall && (
        <section className="space-y-2 rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
          <h2 className="mb-2 font-medium">平均得分（1–5）</h2>
          {Object.entries(overall).map(([k, v]) => (
            <ScoreBar key={k} label={SCORE_LABEL[k]} value={v} />
          ))}
        </section>
      )}

      <section className="space-y-4">
        <h2 className="font-medium">逐题回顾</h2>
        {d.turns.map((t, i) => (
          <article key={i} className="space-y-3 rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
            <div className="flex flex-wrap gap-2 text-xs text-zinc-500">
              <span>{STAGE_LABEL[d.plan!.stages[t.stage_index].kind]}</span>
              <span>· 面试官接着：{ACTION_LABEL[t.action] ?? t.action}</span>
            </div>
            <p className="font-medium">{t.question}</p>
            <p className="whitespace-pre-wrap rounded-lg bg-zinc-50 p-3 text-sm dark:bg-zinc-900">{t.answer}</p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(t.evaluation.scores).map(([k, v]) => (
                <span key={k} className="rounded bg-zinc-100 px-2 py-0.5 text-xs dark:bg-zinc-800">
                  {SCORE_LABEL[k]} {v}
                </span>
              ))}
            </div>
            <List title="亮点" items={t.evaluation.strengths} tone="text-emerald-600" />
            <List title="不足" items={t.evaluation.gaps} tone="text-amber-600" />
            <List title="说得含糊、会被追问的地方" items={t.evaluation.vague_claims} tone="text-red-600" />
          </article>
        ))}
      </section>
    </div>
  )
}
