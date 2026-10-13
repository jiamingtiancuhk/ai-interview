import type { InterviewerRole, Persona, StageKind } from './api'

export const STAGE_LABEL: Record<StageKind, string> = {
  intro: '自我介绍',
  resume_deep_dive: '项目深挖',
  technical: '技术考察',
  behavioral: '行为面试',
  candidate_questions: '反问环节',
}

export const ROLE_LABEL: Record<InterviewerRole, string> = {
  tech_lead: '技术负责人',
  hiring_manager: '业务主管',
  hr: 'HR',
}

export const PERSONA_LABEL: Record<Persona, string> = {
  friendly: '友好',
  neutral: '中性',
  pressure: '压力面',
}

export const ACTION_LABEL: Record<string, string> = {
  follow_up: '追问',
  clarify: '澄清题目',
  next_topic: '换话题',
  next_stage: '进入下一阶段',
  answer_candidate: '回答你的提问',
  wrap_up: '结束面试',
}

export const SCORE_LABEL: Record<string, string> = {
  relevance: '切题',
  depth: '深度',
  evidence: '证据',
  clarity: '清晰',
  structure: '结构',
}

export function fmtTime(s: number): string {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}
