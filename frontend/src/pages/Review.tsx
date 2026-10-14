import { useEffect, useState } from 'react'
import { api, type InterviewDetail, type Report, type Scores } from '../api'
import { ACTION_LABEL, RECOMMENDATION, ROLE_LABEL, SCORE_LABEL, STAGE_LABEL, fmtTime } from '../labels'

const UNSCORED = ['candidate_question', 'clarification_request']

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

function ReportCard({ report }: { report: Report }) {
  const rec = RECOMMENDATION[report.recommendation]
  return (
    <section className="space-y-5 rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-medium">面试官结论</h2>
        <span className={`rounded-full px-3 py-1 text-sm font-medium ${rec.tone}`}>{rec.label}</span>
      </div>
      <p className="leading-relaxed text-zinc-700 dark:text-zinc-300">{report.summary}</p>

      <div className="grid gap-3 sm:grid-cols-2">
        {report.stages.map((st, i) => (
          <div key={i} className="rounded-lg bg-zinc-50 p-3 dark:bg-zinc-900">
            <div className="mb-1 flex items-center justify-between text-sm">
              <span className="font-medium">{STAGE_LABEL[st.kind] ?? st.kind}</span>
              <span className="font-mono tabular-nums text-zinc-500">{st.score}/5</span>
            </div>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">{st.comment}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        <List title="做得好的" items={report.strengths} tone="text-emerald-600" />
        <div>
          <div className="text-xs font-medium text-amber-600">下次面试前要改进的</div>
          <ol className="ml-4 mt-1 list-decimal space-y-2 text-sm text-zinc-700 dark:text-zinc-300">
            {report.improvements.map((im, i) => (
              <li key={i}>
                <div>{im.issue}</div>
                <div className="text-zinc-500">练习：{im.how_to_practice}</div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  )
}

export default function Review({ id }: { id: string }) {
  const [d, setD] = useState<InterviewDetail | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>
    let alive = true
    const load = () =>
      api
        .getInterview(id)
        .then((data) => {
          if (!alive) return
          setD(data)
          // Scoring finishes in the background; poll until it is done.
          if (data.assessing) timer = setTimeout(load, 3000)
        })
        .catch((e) => setError(e.message))
    load()
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [id])

  if (error) return <p className="p-10 text-red-600">{error}</p>
  if (!d) return <p className="p-10 text-zinc-500">加载中…</p>
  if (!d.turns) return <p className="p-10 text-zinc-500">面试还没结束，结束后才能看复盘。</p>

  const scored = d.turns.filter((t) => t.assessment)
  const overall = avg(scored.map((t) => t.assessment!.scores))

  return (
    <div className="mx-auto max-w-3xl space-y-8 px-4 py-10">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">{d.config.job_title} · 复盘</h1>
        <p className="text-sm text-zinc-500">
          {ROLE_LABEL[d.config.interviewer_role]} · 用时 {fmtTime(d.elapsed_s)} · 共 {d.turns.length} 轮问答
        </p>
      </header>

      {d.assessing && (
        <p className="rounded-md bg-zinc-100 px-3 py-2 text-sm text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400">
          {d.report ? '' : scored.length < d.turns.filter((t) => !UNSCORED.includes(t.routing.answer_type)).length ? '正在给每个回答评分…' : '正在写总体评价…'}
          页面会自动更新。
        </p>
      )}

      {d.report && <ReportCard report={d.report} />}

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
        {d.turns.map((t, i) => {
          const a = t.assessment
          return (
            <article key={i} className="space-y-3 rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
              <div className="flex flex-wrap gap-2 text-xs text-zinc-500">
                <span>{STAGE_LABEL[d.plan!.stages[t.stage_index].kind]}</span>
                <span>· 面试官接着：{ACTION_LABEL[t.action] ?? t.action}</span>
              </div>
              <p className="font-medium">{t.question}</p>
              <p className="whitespace-pre-wrap rounded-lg bg-zinc-50 p-3 text-sm dark:bg-zinc-900">{t.answer}</p>
              {a ? (
                <>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(a.scores).map(([k, v]) => (
                      <span key={k} className="rounded bg-zinc-100 px-2 py-0.5 text-xs dark:bg-zinc-800">
                        {SCORE_LABEL[k]} {v}
                      </span>
                    ))}
                  </div>
                  <List title="亮点" items={a.strengths} tone="text-emerald-600" />
                  <List title="不足" items={a.gaps} tone="text-amber-600" />
                  <List title="说得含糊、会被追问的地方" items={a.vague_claims} tone="text-red-600" />
                  {a.better_answer_hint && (
                    <div className="rounded-lg border-l-2 border-zinc-900 bg-zinc-50 p-3 text-sm dark:border-zinc-200 dark:bg-zinc-900">
                      <div className="mb-1 text-xs font-medium text-zinc-500">更好的回答应该包括</div>
                      <p className="whitespace-pre-wrap">{a.better_answer_hint}</p>
                    </div>
                  )}
                </>
              ) : (
                <p className="text-xs text-zinc-400">
                  {UNSCORED.includes(t.routing.answer_type) ? '这一轮是你向面试官提问或请求澄清，不计分。' : '评分中…'}
                </p>
              )}
            </article>
          )
        })}
      </section>
    </div>
  )
}
