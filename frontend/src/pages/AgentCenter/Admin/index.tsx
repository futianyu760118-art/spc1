import React, { useCallback, useEffect, useState } from 'react'
import { Button, Tabs, message } from 'antd'
import {
  ApiOutlined, PlusOutlined, RobotOutlined, SafetyCertificateOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { agentApi } from '../../../services/agent'
import { useAuthStore } from '../../../store/auth'
import PageHeader from '../../../components/Agent/PageHeader'
import StatCard from '../../../components/Agent/StatCard'
import AgentDirectoryTab from './AgentDirectoryTab'
import SkillLibraryTab from './SkillLibraryTab'
import AssistantOpsTab from './AssistantOpsTab'
import BindUsersModal from './BindUsersModal'
import '../agent-center.css'

export default function AgentAdmin() {
  const [stats, setStats] = useState<any>(null)
  const [zone, setZone] = useState('agents')
  const [createSignal, setCreateSignal] = useState(0)
  const [bindOpen, setBindOpen] = useState(false)
  const [bindAgentIds, setBindAgentIds] = useState<number[]>([])
  const hasPermission = useAuthStore((s: any) => s.hasPermission) as (resource: string, action: string) => boolean
  const canConfig = hasPermission('ai.agent.admin', 'update')

  const loadStats = useCallback(async () => {
    try {
      const res: any = await agentApi.adminStats()
      setStats(res.data)
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
    <div className="sc-page ai-center ai-page">
      <PageHeader
        title="智能体管理"
        subtitle="管理智能体目录、技能与助手运营"
        extra={(
          <div style={{ display: 'flex', gap: 8 }}>
            <Button onClick={() => openBindUsers()}>批量绑定用户</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建智能体</Button>
          </div>
        )}
      />

      <div className="ai-stat-grid">
        <StatCard icon={<RobotOutlined />} label="智能体总数" value={stats?.agents || 0} unit="个" />
        <StatCard icon={<SafetyCertificateOutlined />} label="启用智能体" value={stats?.active_agents || 0} unit="个" accent="#16a34a" accentBg="#f0fdf4" />
        <StatCard icon={<ApiOutlined />} label="能力调用" value={callTotal.toLocaleString('zh-CN')} unit="次" accent="#0284c7" accentBg="#f0f9ff" />
        <StatCard icon={<ThunderboltOutlined />} label="失败 / 超时 / 拒绝" value={callFailed.toLocaleString('zh-CN')} unit="次" accent="#dc2626" accentBg="#fef2f2" />
      </div>

      <Tabs
        activeKey={zone}
        onChange={setZone}
        items={[
          {
            key: 'agents',
            label: '智能体',
            children: (
              <AgentDirectoryTab
                createSignal={createSignal}
                onCreateConsumed={() => setCreateSignal(0)}
                onBindUsers={openBindUsers}
              />
            ),
          },
          {
            key: 'skills',
            label: '技能库',
            children: <SkillLibraryTab />,
          },
          {
            key: 'ops',
            label: '助手运营',
            children: <AssistantOpsTab canConfig={canConfig} />,
          },
        ]}
      />

      <BindUsersModal
        open={bindOpen}
        preselectedAgentIds={bindAgentIds}
        onClose={() => setBindOpen(false)}
        onSuccess={loadStats}
      />
    </div>
  )
}
