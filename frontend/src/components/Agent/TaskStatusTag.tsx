import React from 'react'
import { Tag, Tooltip } from 'antd'
import type { AgentTaskStatus, AgentTaskPriority, AgentAnalysisStatus } from '../../services/agent'

const STATUS_META: Record<AgentTaskStatus, { color: string; text: string }> = {
  pending: { color: 'default', text: '待处理' },
  in_progress: { color: 'processing', text: '处理中' },
  blocked: { color: 'warning', text: '阻塞' },
  completed: { color: 'success', text: '已完成' },
  cancelled: { color: 'default', text: '已取消' },
}

const PRIORITY_META: Record<AgentTaskPriority, { color: string; text: string }> = {
  low: { color: 'default', text: '低' },
  normal: { color: 'blue', text: '普通' },
  high: { color: 'orange', text: '高' },
  urgent: { color: 'red', text: '紧急' },
}

const ANALYSIS_META: Record<AgentAnalysisStatus, { color: string; text: string }> = {
  pending: { color: 'default', text: '待分析' },
  running: { color: 'processing', text: '分析中' },
  done: { color: 'success', text: '已分析' },
  failed: { color: 'error', text: '分析失败' },
  skipped: { color: 'default', text: '无需分析' },
}

export const TaskStatusTag: React.FC<{ status: AgentTaskStatus; isOverdue?: boolean }> = ({ status, isOverdue }) => {
  const meta = STATUS_META[status] || { color: 'default', text: status }
  return (
    <>
      <Tag color={meta.color}>{meta.text}</Tag>
      {isOverdue && status !== 'completed' && status !== 'cancelled' && (
        <Tooltip title="已超过截止时间">
          <Tag color="red">逾期</Tag>
        </Tooltip>
      )}
    </>
  )
}

export const TaskPriorityTag: React.FC<{ priority: AgentTaskPriority }> = ({ priority }) => {
  const meta = PRIORITY_META[priority] || { color: 'default', text: priority }
  return <Tag color={meta.color}>{meta.text}</Tag>
}

export const TaskAnalysisTag: React.FC<{ status: AgentAnalysisStatus }> = ({ status }) => {
  const meta = ANALYSIS_META[status] || { color: 'default', text: status }
  return <Tag color={meta.color}>{meta.text}</Tag>
}
