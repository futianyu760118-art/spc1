export type ClarificationQuestionType = 'single' | 'multiple' | 'text'

export interface ClarificationOption {
  value: string
  label: string
}

export interface ClarificationQuestion {
  id: string
  type: ClarificationQuestionType
  label: string
  options?: ClarificationOption[]
  placeholder?: string
  required?: boolean
}

export interface ClarificationSpec {
  title?: string
  questions: ClarificationQuestion[]
  submitLabel?: string
}

const CLARIFICATION_BLOCK_RE = /```(?:spc-confirm|spc_confirmation)\s*([\s\S]*?)```/i
const OPEN_CLARIFICATION_RE = /```(?:spc-confirm|spc_confirmation)[\s\S]*$/i

function normalizeOption(raw: unknown, index: number): ClarificationOption | null {
  if (typeof raw === 'string') {
    return raw.trim() ? { value: raw.trim(), label: raw.trim() } : null
  }
  if (!raw || typeof raw !== 'object') return null
  const record = raw as Record<string, unknown>
  const label = String(record.label ?? record.value ?? '').trim()
  const value = String(record.value ?? record.label ?? index).trim()
  if (!label || !value) return null
  return { value, label }
}

export function parseClarification(content: string): ClarificationSpec | null {
  const match = (content || '').match(CLARIFICATION_BLOCK_RE)
  if (!match) return null
  let payload: unknown
  try {
    payload = JSON.parse(match[1].trim())
  } catch {
    return null
  }
  if (!payload || typeof payload !== 'object') return null
  const record = payload as Record<string, unknown>
  const rawQuestions = Array.isArray(record.questions) ? record.questions : []
  const questions: ClarificationQuestion[] = []
  rawQuestions.slice(0, 10).forEach((raw, index) => {
    if (!raw || typeof raw !== 'object') return
    const item = raw as Record<string, unknown>
    const type = String(item.type || '').trim()
    const label = String(item.label || '').trim()
    if (!label || !['single', 'multiple', 'text'].includes(type)) return
    const options = Array.isArray(item.options)
      ? item.options.map(normalizeOption).filter((option): option is ClarificationOption => Boolean(option))
      : []
    if ((type === 'single' || type === 'multiple') && options.length === 0) return
    questions.push({
      id: String(item.id || `q${index + 1}`),
      type: type as ClarificationQuestionType,
      label,
      options: options.length > 0 ? options : undefined,
      placeholder: item.placeholder ? String(item.placeholder) : undefined,
      required: item.required !== false,
    })
  })
  return questions.length > 0
    ? {
        title: record.title ? String(record.title) : undefined,
        submitLabel: record.submit_label ? String(record.submit_label) : undefined,
        questions,
      }
    : null
}

export function stripClarificationBlock(content: string): string {
  return (content || '')
    .replace(new RegExp(CLARIFICATION_BLOCK_RE.source, 'gi'), '')
    .replace(OPEN_CLARIFICATION_RE, '')
    .trim()
}
