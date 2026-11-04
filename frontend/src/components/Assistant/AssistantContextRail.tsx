import React from 'react'
import { Button } from 'antd'
import { RightOutlined } from '@ant-design/icons'
import { ChatMessage } from './useAssistantChat'
import { TeamAgent } from './types'

interface Props {
  teamAgents: TeamAgent[]
  messages: ChatMessage[]
  onCollapse: () => void
}

const STEP_STATUS_META: Record<string, { cls: string; text: string }> = {
  running: { cls: 'running', text: '执行中' },
  completed: { cls: 'done', text: '完成' },
  failed: { cls: 'failed', text: '失败' },
  blocked: { cls: 'blocked', text: '已拦截' },
  pending_confirmation: { cls: 'pending', text: '待确认' },
  cancelled: { cls: 'muted', text: '已取消' },
}

export default function AssistantContextRail({ teamAgents, messages, onCollapse }: Props) {
  const capabilities = Array.from(new Map(
    teamAgents.flatMap(agent => agent.capabilities || []).map(item => [item.code, item.name]),
  ).entries())
  const skills = Array.from(new Map(
    teamAgents.flatMap(agent => (agent.skills || []).map(skill => [`${skill.id}-${skill.name}`, skill.name])),
  ).entries())

  const latest = [...messages].reverse().find(
    message => message.role === 'assistant' && (message.plan || (message.steps && message.steps.length > 0)),
  )

  return (
    <aside className="ai-chat-context">
      <div className="ai-context-head">
        <strong>本会话上下文</strong>
        <Button type="text" size="small" icon={<RightOutlined />} onClick={onCollapse} title="收起上下文" />
      </div>
      <div className="ai-context-body">
        <section className="ai-context-section">
          <h4>团队成员</h4>
          {teamAgents.length === 0 ? (
            <div className="ai-context-empty">还没有团队成员，去「我的助手」添加</div>
          ) : (
            <div className="ai-context-team">
              {teamAgents.map(agent => (
                <div key={agent.id} className="ai-context-team-row">
                  <div className="ai-avatar sm">{(agent.name || '?').slice(0, 1)}</div>
                  <span className="ai-context-team-name">{agent.name}</span>
                  <span className="ai-context-team-count">{(agent.capabilities || []).length} 项能力</span>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="ai-context-section">
          <h4>已启用能力</h4>
          {capabilities.length === 0 && skills.length === 0 ? (
            <div className="ai-context-empty">暂无能力或技能</div>
          ) : (
            <div className="ai-tag-list">
              {capabilities.map(([code, name]) => (
                <span key={code} className="sc-tag sc-tag-kit">{name}</span>
              ))}
              {skills.map(([key, name]) => (
                <span key={key} className="sc-tag sc-tag-purple">{name}</span>
              ))}
            </div>
          )}
        </section>

        <section className="ai-context-section">
          <h4>执行链</h4>
          {!latest ? (
            <div className="ai-context-empty">发起对话后，这里会显示助手的计划与执行步骤</div>
          ) : (
            <div className="ai-context-trace">
              {latest.plan && (
                <div className="ai-context-plan">
                  <div className="ai-context-plan-title">
                    {latest.plan.status === 'planning' ? '正在规划…' : '执行计划'}
                  </div>
                  {latest.plan.status === 'ready' && (
                    <ol>
                      {latest.plan.steps.map((step, index) => <li key={index}>{step}</li>)}
                    </ol>
                  )}
                </div>
              )}
              {(latest.steps || []).length > 0 && (
                <div className="ai-context-steps">
                  {latest.steps!.map(step => {
                    const meta = STEP_STATUS_META[step.status] || { cls: 'muted', text: step.status }
                    return (
                      <div key={step.step_id} className="ai-context-step">
                        <span className={`ai-step-dot ${meta.cls}`} />
                        <span className="ai-context-step-label">
                          {step.agent_label || step.tool}
                        </span>
                        <span className={`ai-step-state ${meta.cls}`}>{meta.text}</span>
                        {step.duration_ms != null && (
                          <span className="ai-context-step-time">{Math.round(step.duration_ms)}ms</span>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}
        </section>
      </div>
      <div className="ai-context-note">
        上下文 {messages.length} 条消息 · {teamAgents.length} 位成员
      </div>
    </aside>
  )
}
