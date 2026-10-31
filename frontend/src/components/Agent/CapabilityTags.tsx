import React from 'react'
import { Space, Tag } from 'antd'
import { AgentCapabilityItem } from '../../services/agent'

interface CapabilityTagsProps {
  items?: AgentCapabilityItem[] | null
  max?: number
}

export function CapabilityTags({ items, max = 3 }: CapabilityTagsProps) {
  const list = items || []
  return (
    <Space size={4} wrap>
      {list.slice(0, max).map(item => (
        <Tag key={item.code} style={{ marginInlineEnd: 0 }}>{item.name}</Tag>
      ))}
      {list.length > max && <Tag style={{ marginInlineEnd: 0 }}>+{list.length - max}</Tag>}
      {list.length === 0 && <Tag style={{ marginInlineEnd: 0 }}>无</Tag>}
    </Space>
  )
}
