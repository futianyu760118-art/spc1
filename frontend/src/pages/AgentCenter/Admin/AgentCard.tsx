import React from 'react'
import { AgentInfo, AgentSkillBrief } from '../../../services/agent'

interface Props {
  agent: AgentInfo
  onEdit: (agent: AgentInfo) => void
}

export default function AgentCard({ agent, onEdit }: Props) {
  const capabilities = agent.capabilities || []
  const skills: AgentSkillBrief[] = agent.skills || []
  const totalTags = capabilities.length + skills.length

  return (
    <div
      className="ai-agent-card"
      role="button"
      tabIndex={0}
      onClick={() => onEdit(agent)}
      onKeyDown={event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onEdit(agent)
        }
      }}
      style={{ cursor: 'pointer' }}
    >
      <div className="ai-agent-top">
        <div className="ai-avatar">{(agent.name || '?').slice(0, 1)}</div>
        <div className="ai-agent-title">
          <div className="ai-agent-name-row">
            <span className="ai-agent-name">{agent.name}</span>
            <span className="ai-agent-no">{agent.agent_no}</span>
          </div>
        </div>
        <span className={`sc-tag ${agent.status === 'active' ? 'sc-tag-done' : 'sc-tag-wait'}`}>
          {agent.status === 'active' ? '启用' : '停用'}
        </span>
      </div>

      <div className="ai-agent-desc">{agent.description || '暂无说明'}</div>

      <div className="ai-agent-tags">
        {capabilities.slice(0, 2).map(capability => (
          <span key={capability.code} className="sc-tag sc-tag-kit">{capability.name}</span>
        ))}
        {skills.slice(0, 1).map(skill => (
          <span key={skill.id} className="sc-tag sc-tag-purple">{skill.name}</span>
        ))}
        {totalTags > 3 && <span className="sc-tag sc-tag-plain">+{totalTags - 3}</span>}
        {totalTags === 0 && <span className="ai-muted">未配置能力</span>}
      </div>

      <div className="ai-agent-foot">
        <span>{agent.scope_type === 'roles' ? `指定角色 × ${agent.scope_role_ids?.length || 0}` : '所有人可勾选'} · 团队 {agent.teams_count || 0}</span>
        <button
          type="button"
          className="ai-agent-edit"
          onClick={event => { event.stopPropagation(); onEdit(agent) }}
        >
          编辑
        </button>
      </div>
    </div>
  )
}
