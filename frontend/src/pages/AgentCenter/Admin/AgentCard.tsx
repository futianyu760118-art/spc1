import React from 'react'
import { Button } from 'antd'
import { AgentInfo, AgentSkillBrief } from '../../../services/agent'
import { CapabilityTags } from '../../../components/Agent/CapabilityTags'

interface Props {
  agent: AgentInfo
  onEdit: (agent: AgentInfo) => void
  onBindUsers: (agent: AgentInfo) => void
}

export default function AgentCard({ agent, onEdit, onBindUsers }: Props) {
  const skills: AgentSkillBrief[] = agent.skills || []

  return (
    <div
      className="ai-agent-card"
      onClick={() => onEdit(agent)}
      style={{ cursor: 'pointer' }}
    >
      <div className="ai-agent-top">
        <div className="ai-avatar">{(agent.name || '?').slice(0, 1)}</div>
        <div className="ai-agent-title">
          <div className="ai-agent-name">{agent.name}</div>
          <div className="ai-agent-no">{agent.agent_no}</div>
        </div>
        <span className={`sc-tag ${agent.status === 'active' ? 'sc-tag-done' : 'sc-tag-wait'}`}>
          {agent.status === 'active' ? '启用' : '停用'}
        </span>
      </div>

      <div className="ai-agent-desc">{agent.description || '暂无说明'}</div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <CapabilityTags items={agent.capabilities} max={2} />
        {skills.length > 0 && (
          <span className="ai-tag-list">
            {skills.slice(0, 2).map(skill => (
              <span key={skill.id} className="sc-tag sc-tag-purple">{skill.name}</span>
            ))}
            {skills.length > 2 && <span className="sc-tag sc-tag-plain">+{skills.length - 2}</span>}
          </span>
        )}
      </div>

      <div className="ai-agent-foot">
        <span>{agent.scope_type === 'roles' ? `指定角色 × ${agent.scope_role_ids?.length || 0}` : '所有人可勾选'}</span>
        <span>团队 {agent.teams_count || 0}</span>
        <div className="ai-more">
          <Button
            type="link"
            size="small"
            onClick={event => { event.stopPropagation(); onEdit(agent) }}
          >
            编辑
          </Button>
          <Button
            type="link"
            size="small"
            onClick={event => { event.stopPropagation(); onBindUsers(agent) }}
          >
            绑定用户
          </Button>
        </div>
      </div>
    </div>
  )
}
