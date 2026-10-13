import { useEffect, useState } from 'react'
import { api, type InterviewConfig, type InterviewerRole, type Language, type Persona } from '../api'
import { PERSONA_LABEL, ROLE_LABEL } from '../labels'
import { navigate } from '../router'

const DEFAULTS: InterviewConfig = {
  job_title: '',
  language: 'zh',
  persona: 'neutral',
  interviewer_role: 'tech_lead',
  difficulty: 'intermediate',
  duration_min: 30,
  job_description: '',
  resume_text: '',
}

function Segmented<T extends string | number>(props: {
  value: T
  options: { value: T; label: string }[]
  onChange: (v: T) => void
}) {
  return (
    <div className="inline-flex flex-wrap rounded-lg bg-zinc-100 p-1 dark:bg-zinc-800">
      {props.options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => props.onChange(o.value)}
          className={`rounded-md px-3 py-1.5 text-sm transition ${
            props.value === o.value
              ? 'bg-white font-medium text-zinc-900 shadow-sm dark:bg-zinc-600 dark:text-white'
              : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

function Field(props: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <div className="text-sm font-medium text-zinc-800 dark:text-zinc-200">
        {props.label}
        {props.hint && <span className="ml-2 font-normal text-zinc-500">{props.hint}</span>}
      </div>
      {props.children}
    </div>
  )
}

function DocInput(props: { label: string; value: string; onChange: (v: string) => void; placeholder: string }) {
  const [status, setStatus] = useState('')
  async function onFile(f: File | undefined) {
    if (!f) return
    setStatus(`正在读取 ${f.name}…`)
    try {
      const { text } = await api.parseDocument(f)
      props.onChange(text)
      setStatus(`已读取 ${f.name}（${text.length} 字）`)
    } catch (e) {
      setStatus(`读取失败：${(e as Error).message}`)
    }
  }
  return (
    <Field label={props.label} hint="可选，PDF / DOCX / TXT 或直接粘贴">
      <textarea
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        placeholder={props.placeholder}
        rows={5}
        className="input resize-y"
      />
      <div className="flex items-center gap-3 text-sm">
        <label className="cursor-pointer rounded-md border border-zinc-300 px-3 py-1 hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800">
          上传文件
          <input type="file" accept=".pdf,.docx,.txt,.md" className="hidden" onChange={(e) => onFile(e.target.files?.[0])} />
        </label>
        <span className="text-zinc-500">{status}</span>
      </div>
    </Field>
  )
}

export default function Setup() {
  const [cfg, setCfg] = useState<InterviewConfig>(DEFAULTS)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [llm, setLlm] = useState<{ ok: boolean; model: string; model_ready: boolean } | null>(null)

  useEffect(() => {
    api.health().then((h) => setLlm(h.llm)).catch(() => setLlm({ ok: false, model: '?', model_ready: false }))
  }, [])

  const set = <K extends keyof InterviewConfig>(k: K, v: InterviewConfig[K]) => setCfg((c) => ({ ...c, [k]: v }))

  async function start() {
    setBusy(true)
    setError('')
    try {
      const snap = await api.createInterview(cfg)
      navigate(`/interview/${snap.session_id}`)
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8 px-4 py-10">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">开始一场模拟面试</h1>
        <p className="text-zinc-500">
          面试官会根据你的简历和职位描述提前出一份面试计划，分阶段提问，并在回答不够具体时继续追问。全程在本机运行。
        </p>
        {llm && !llm.model_ready && (
          <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-300">
            {llm.ok ? `模型 ${llm.model} 还没下载完，面试暂时无法开始。` : '连不上 Ollama，请确认 Ollama 已经打开。'}
          </p>
        )}
      </header>

      <Field label="应聘岗位">
        <input
          value={cfg.job_title}
          onChange={(e) => set('job_title', e.target.value)}
          placeholder="例如：后端开发工程师 / Data Scientist"
          className="input"
        />
      </Field>

      <div className="grid gap-6 sm:grid-cols-2">
        <Field label="面试语言">
          <Segmented<Language>
            value={cfg.language}
            onChange={(v) => set('language', v)}
            options={[{ value: 'zh', label: '中文' }, { value: 'en', label: 'English' }]}
          />
        </Field>
        <Field label="时长">
          <Segmented<number>
            value={cfg.duration_min}
            onChange={(v) => set('duration_min', v)}
            options={[20, 30, 45].map((m) => ({ value: m, label: `${m} 分钟` }))}
          />
        </Field>
        <Field label="面试官">
          <Segmented<InterviewerRole>
            value={cfg.interviewer_role}
            onChange={(v) => set('interviewer_role', v)}
            options={(['tech_lead', 'hiring_manager', 'hr'] as const).map((r) => ({ value: r, label: ROLE_LABEL[r] }))}
          />
        </Field>
        <Field label="风格">
          <Segmented<Persona>
            value={cfg.persona}
            onChange={(v) => set('persona', v)}
            options={(['friendly', 'neutral', 'pressure'] as const).map((p) => ({ value: p, label: PERSONA_LABEL[p] }))}
          />
        </Field>
        <Field label="难度">
          <Segmented<string>
            value={cfg.difficulty}
            onChange={(v) => set('difficulty', v)}
            options={[
              { value: 'junior', label: '初级' },
              { value: 'intermediate', label: '中级' },
              { value: 'senior', label: '高级' },
            ]}
          />
        </Field>
      </div>

      <DocInput label="简历" value={cfg.resume_text} onChange={(v) => set('resume_text', v)} placeholder="粘贴简历内容，面试官会挑你的项目深挖" />
      <DocInput label="职位描述 (JD)" value={cfg.job_description} onChange={(v) => set('job_description', v)} placeholder="粘贴 JD，面试官会重点考察你和岗位要求的差距" />

      {error && <p className="text-sm text-red-600">{error}</p>}
      <button
        disabled={!cfg.job_title.trim() || busy || llm?.model_ready === false}
        onClick={start}
        className="w-full rounded-lg bg-zinc-900 py-3 font-medium text-white transition hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
      >
        {busy ? '面试官正在看你的简历、准备问题…' : '开始面试'}
      </button>
    </div>
  )
}
