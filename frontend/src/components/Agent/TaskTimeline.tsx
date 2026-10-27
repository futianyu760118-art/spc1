import React from 'react'
import { Empty, Timeline, Typography } from 'antd'
import type { AgentTaskEvent } from '../../services/agent'

const { Text } = Typography

const EVENT_LABELS: Record<string, string> = {
  created: '任务创建',
  analysis_started: '开始自动分析',
  analysis_completed: '自动分析完成',
  analysis_failed: '自动分析失败',
  started: '开始处理',
  blocked: '标记阻塞',
  resumed: '恢复处理',
  submitted: '提交汇报',
  returned: '退回重做',
  reopened: '重新打开',
  updated: '任务更新',
  reminded: '催办',
  reassigned: '改派',
  cancelled: '取消任务',
}

function eventDetail(event: AgentTaskEvent): string {
  const payload = event.payload || {}
  if (payload.reason) return String(payload.reason)
  if (payload.summary) return String(payload.summary)
  if (payload.changes) return `变更：${JSON.stringify(payload.changes)}`
  if (payload.action) return String(payload.action)
  if (payload.by) return String(payload.by)
  return ''
}

export const TaskTimeline: React.FC<{ events: AgentTaskEvent[] }> = ({ events }) => {
  if (!events?.length) return <Empty description="暂无动态" />
  return (
    <Timeline
      items={events.map(event => ({
        color: event.event_type.includes('failed') || event.event_type === 'cancelled' ? 'red' : 'blue',
        children: (
          <div style={{ fontSize: 13 }}>
            <Text strong>{EVENT_LABELS[event.event_type] || event.event_type}</Text>
            <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
              {event.created_at ? new Date(event.created_at).toLocaleString('zh-CN') : ''}
            </Text>
            {event.from_status && event.to_status && event.from_status !== event.to_status && (
              <div style={{ fontSize: 12, color: '#64748b' }}>
                {event.from_status} → {event.to_status}
              </div>
            )}
            {eventDetail(event) && <div style={{ fontSize: 12, color: '#475569' }}>{eventDetail(event)}</div>}
          </div>
        ),
      }))}
    />
  )
}
