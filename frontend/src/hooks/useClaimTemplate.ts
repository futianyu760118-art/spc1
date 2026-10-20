import { useEffect, useState } from 'react'
import { qualityApi } from '../services/quality'

export type ClaimTemplate = {
  clauses: string[]
  claim_method_default: string
}

const EMPTY: ClaimTemplate = { clauses: [], claim_method_default: '' }
let cached: ClaimTemplate | null = null
let pending: Promise<ClaimTemplate> | null = null

function loadClaimTemplate(): Promise<ClaimTemplate> {
  if (cached) return Promise.resolve(cached)
  if (!pending) {
    pending = qualityApi.template()
      .then((res: any) => {
        const next: ClaimTemplate = {
          clauses: Array.isArray(res?.data?.clauses) ? res.data.clauses : [],
          claim_method_default: res?.data?.claim_method_default || '',
        }
        cached = next
        return next
      })
      .catch(() => EMPTY)
      .finally(() => { pending = null })
  }
  return pending
}

export function useClaimTemplate(enabled = true): ClaimTemplate {
  const [template, setTemplate] = useState<ClaimTemplate>(cached || EMPTY)

  useEffect(() => {
    if (!enabled) return
    if (cached) {
      setTemplate(cached)
      return
    }
    let alive = true
    loadClaimTemplate().then(t => { if (alive) setTemplate(t) })
    return () => { alive = false }
  }, [enabled])

  return template
}
