import React from 'react'
import { AgentCapabilityItem } from '../../services/agent'

interface CapabilityTagsProps {
  items?: AgentCapabilityItem[] | null
  max?: number
  emptyText?: string
}

export function CapabilityTags({ items, max = 3, emptyText = '未配置能力' }: CapabilityTagsProps) {
  const list = items || []
  return (
    <span className="ai-tag-list">
      {list.slice(0, max).map(item => (
        <span key={item.code} className="sc-tag sc-tag-plain">{item.name}</span>
      ))}
      {list.length > max && <span className="sc-tag sc-tag-plain">+{list.length - max}</span>}
      {list.length === 0 && <span className="ai-muted">{emptyText}</span>}
    </span>
  )
}
