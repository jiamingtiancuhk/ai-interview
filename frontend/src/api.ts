export type Language = 'zh' | 'en'
export type Persona = 'friendly' | 'neutral' | 'pressure'
export type InterviewerRole = 'hr' | 'tech_lead' | 'hiring_manager'
export type StageKind = 'intro' | 'resume_deep_dive' | 'technical' | 'behavioral' | 'candidate_questions'

export interface InterviewConfig {
  job_title: string
  language: Language
  persona: Persona
  interviewer_role: InterviewerRole
  difficulty: string
  duration_min: number
  job_description: string
  resume_text: string
}

export interface Snapshot {
  session_id: string
  stage_index: number
  stage_kind: StageKind
  topic_index: number
  stages: { kind: StageKind; minutes: number; topics: number }[]
  elapsed_s: number
  duration_s: number
  finished: boolean
}

export interface Message {
  role: 'interviewer' | 'candidate'
  content: string
  stage_index: number
  topic_index: number
  elapsed_s: number
}

export interface Scores {
  relevance: number
  depth: number
  evidence: number
  clarity: number
  structure: number
}

export interface Assessment {
  scores: Scores
  strengths: string[]
  gaps: string[]
  vague_claims: string[]
  better_answer_hint: string
}

export interface Turn {
  stage_index: number
  topic_index: number
  question: string
  answer: string
  action: string
  route_latency_s: number
  routing: { answer_type: string; needs_follow_up: boolean; probe_angle: string }
  assessment: Assessment | null
}

export interface InterviewDetail extends Snapshot {
  config: Omit<InterviewConfig, 'job_description' | 'resume_text'>
  messages: Message[]
  turns?: Turn[]
  assessing?: boolean
  plan?: { stages: { kind: StageKind; goal: string; minutes: number; topics: { title: string; rationale: string }[] }[] }
}

export interface Health {
  llm: { ok: boolean; model: string; model_ready: boolean; error?: string }
  asr: { state: 'loading' | 'ready' | 'unavailable'; model: string; error: string }
}

export interface InterviewSummary {
  id: string
  created_at: number
  elapsed_s: number
  finished: number
  job_title: string
  language: Language
  interviewer_role: InterviewerRole
  persona: Persona
}

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = r.statusText
    try {
      detail = (await r.json()).detail ?? detail
    } catch {
      /* not JSON */
    }
    throw new Error(detail)
  }
  return r.json()
}

export const api = {
  health: () => fetch('/api/health').then(json<Health>),
  parseDocument: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch('/api/documents/parse', { method: 'POST', body: fd }).then(json<{ text: string }>)
  },
  createInterview: (cfg: InterviewConfig) =>
    fetch('/api/interviews', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg),
    }).then(json<Snapshot>),
  listInterviews: () => fetch('/api/interviews').then(json<InterviewSummary[]>),
  getInterview: (id: string) => fetch(`/api/interviews/${id}`).then(json<InterviewDetail>),
}

export type ServerEvent =
  | ({ type: 'state' } & Snapshot)
  | { type: 'history'; messages: Message[] }
  | { type: 'thinking' }
  | { type: 'interviewer_delta'; text: string }
  | { type: 'interviewer_done'; text: string }
  | { type: 'transcript_segment'; text: string; latency_s: number }
  | { type: 'finished' }
  | { type: 'error'; message: string }

export function interviewSocket(id: string): WebSocket {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return new WebSocket(`${proto}://${location.host}/api/interviews/${id}/ws`)
}
