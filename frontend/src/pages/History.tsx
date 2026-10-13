import { useEffect, useState } from 'react'
import { api, type InterviewSummary } from '../api'
import { PERSONA_LABEL, ROLE_LABEL, fmtTime } from '../labels'
import { navigate } from '../router'

export default function History() {
  const [rows, setRows] = useState<InterviewSummary[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.listInterviews().then(setRows).catch((e) => setError(e.message))
  }, [])

  return (
    <div className="mx-auto max-w-2xl space-y-6 px-4 py-10">
      <h1 className="text-2xl font-semibold">面试记录</h1>
      {error && <p className="text-red-600">{error}</p>}
      {rows?.length === 0 && <p className="text-zinc-500">还没有面试记录。</p>}
      <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
        {rows?.map((r) => (
          <li key={r.id}>
            <button
              onClick={() => navigate(r.finished ? `/review/${r.id}` : `/interview/${r.id}`)}
              className="flex w-full items-center gap-3 py-4 text-left hover:bg-zinc-50 dark:hover:bg-zinc-900"
            >
              <div className="flex-1">
                <div className="font-medium">{r.job_title}</div>
                <div className="text-sm text-zinc-500">
                  {new Date(r.created_at * 1000).toLocaleString()} · {ROLE_LABEL[r.interviewer_role]} · {PERSONA_LABEL[r.persona]} ·{' '}
                  {fmtTime(r.elapsed_s)}
                </div>
              </div>
              <span className={`rounded-full px-2 py-0.5 text-xs ${r.finished ? 'bg-zinc-100 dark:bg-zinc-800' : 'bg-amber-100 text-amber-800'}`}>
                {r.finished ? '已完成' : '继续面试'}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
