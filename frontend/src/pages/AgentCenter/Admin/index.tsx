import React, { useCallback, useEffect, useState } from 'react'
import { message } from 'antd'
import { PlusOutlined, TeamOutlined } from '@ant-design/icons'
import { agentApi } from '../../../services/agent'
import { useAuthStore } from '../../../store/auth'
import PageHeader from '../../../components/Agent/PageHeader'
import AgentDirectoryTab from './AgentDirectoryTab'
import SkillLibraryTab from './SkillLibraryTab'
import AssistantOpsTab from './AssistantOpsTab'
import BindUsersModal from './BindUsersModal'
import '../agent-center.css'
import '../agent-center-v3.css'

type AdminZone = 'agents' | 'skills' | 'ops'

export default function AgentAdmin() {
  const [stats, setStats] = useState<any>(null)
  const [skillsTotal, setSkillsTotal] = useState(0)
  const [zone, setZone] = useState<AdminZone>('agents')
  const [createSignal, setCreateSignal] = useState(0)
  const [bindOpen, setBindOpen] = useState(false)
  const [bindAgentIds, setBindAgentIds] = useState<number[]>([])
  const hasPermission = useAuthStore((s: any) => s.hasPermission) as (resource: string, action: string) => boolean
  const canConfig = hasPermission('ai.agent.admin', 'update')

  const loadStats = useCallback(async () => {
    try {
      const [statsRes, skillsRes]: any = await Promise.all([
        agentApi.adminStats(),
        agentApi.adminSkills({ page: 1, page_size: 1 }).catch(() => ({ data: { total: 0 } })),
      ])
      setStats(statsRes.data)
      setSkillsTotal(Number(skillsRes.data?.total || 0))
    } catch (e: any) {
      message.error(String(e?.message || e))
    }
  }, [])

  useEffect(() => { loadStats() }, [loadStats])

  const callTotal = Object.values(stats?.calls_by_status || {}).reduce(
    (sum: number, value: any) => sum + Number(value || 0), 0,
  )
  const callFailed = ['failed', 'timeout', 'rejected'].reduce(
    (sum, key) => sum + Number((stats?.calls_by_status || {})[key] || 0), 0,
  )

  const openCreate = () => {
    setZone('agents')
    setCreateSignal(value => value + 1)
  }

  const openBindUsers = (agentIds: number[] = []) => {
    setBindAgentIds(agentIds)
    setBindOpen(true)
  }

  return (
    <div className="sc-page ai-center ai-page ac-page">
      <PageHeader
        title="智能体管理"
        extra={canConfig ? (
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="ac-btn" onClick={() => openBindUsers()}>
              <TeamOutlined /> 批量绑定用户
            </button>
            <button type="button" className="ac-btn primary" onClick={openCreate}>
              <PlusOutlined /> 新建智能体
            </button>
          </div>
        ) : undefined}
      />

      <div className="ac-stat-strip">
        <div className="ac-stat"><b>{stats?.agents || 0}</b><span>智能体</span></div>
        <div className="ac-stat"><b>{stats?.active_agents || 0}</b><span>已启用</span></div>
        <div className="ac-stat"><b>{callTotal.toLocaleString('zh-CN')}</b><span>能力调用</span></div>
        <div className="ac-stat"><b>{callFailed.toLocaleString('zh-CN')}</b><span>异常调用</span></div>
        <div className="ac-stat"><b>{skillsTotal}</b><span>技能</span></div>
        <div className="ac-stat-note"><i className="ac-live-dot" />目录数据实时加载</div>
      </div>

      <nav className="ac-admin-tabs" aria-label="智能体管理分区">
        <button
          type="button"
          className={zone === 'agents' ? 'active' : ''}
          onClick={() => setZone('agents')}
        >
          智能体<span className="ac-count">{stats?.agents || 0}</span>
        </button>
        <button
          type="button"
          className={zone === 'skills' ? 'active' : ''}
          onClick={() => setZone('skills')}
        >
          技能库<span className="ac-count">{skillsTotal}</span>
        </button>
        <button
          type="button"
          className={zone === 'ops' ? 'active' : ''}
          onClick={() => setZone('ops')}
        >
          助手运营<span className="ac-count">30d</span>
        </button>
      </nav>

      {zone === 'agents' && (
        <AgentDirectoryTab
          stats={stats}
          canManage={canConfig}
          createSignal={createSignal}
          onCreateConsumed={() => setCreateSignal(0)}
          onBindUsers={openBindUsers}
          onChanged={loadStats}
          onOpenOps={() => setZone('ops')}
        />
      )}
      {zone === 'skills' && (
        <SkillLibraryTab
          canManage={canConfig}
          onOpenAgents={() => setZone('agents')}
          onChanged={loadStats}
        />
      )}
      {zone === 'ops' && <AssistantOpsTab canConfig={canConfig} />}

      <BindUsersModal
        open={bindOpen}
        preselectedAgentIds={bindAgentIds}
        onClose={() => setBindOpen(false)}
        onSuccess={loadStats}
      />
    </div>
  )
}
