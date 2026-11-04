import React, { useCallback, useEffect, useState } from 'react'
import {
  Button, Drawer, Empty, List, Popconfirm, Space, Spin, Table, message,
} from 'antd'
import {
  HistoryOutlined, MessageOutlined, PlusOutlined,
  TeamOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { agentApi, AgentCall, AgentSkillBrief, TeamMember } from '../../../services/agent'
import { CapabilityTags } from '../../../components/Agent/CapabilityTags'
import PageHeader from '../../../components/Agent/PageHeader'
import StatCard from '../../../components/Agent/StatCard'
import Markdown from '../../../components/Markdown'
import { useAuthStore } from '../../../store/auth'
import AddMemberDrawer from './AddMemberDrawer'
import '../agent-center.css'

interface ConversationItem {
  id: number
  title?: string
  status?: string
  last_message_at?: string
}

const CALL_STATUS_META: Record<string, { cls: string; text: string }> = {
  success: { cls: 'sc-tag-done', text: '成功' },
  failed: { cls: 'sc-tag-danger', text: '失败' },
  timeout: { cls: 'sc-tag-warn', text: '超时' },
  rejected: { cls: 'sc-tag-plain', text: '拒绝' },
  running: { cls: 'sc-tag-kit', text: '进行中' },
}

function formatNumber(value: number): string {
  return value.toLocaleString('zh-CN')
}

function formatTime(value?: string): string {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

function TeamMembersCard(props: {
  team: TeamMember[]
  canManage: boolean
  onAdd: () => void
  onRemove: (agentId: number) => void
}) {
  const { team, canManage, onAdd, onRemove } = props
  return (
    <section className="ai-card">
      <div className="ai-card-head">
        <h3>团队成员</h3>
        <span className="ai-hint">成员的技能与能力决定助手能做什么</span>
        {canManage && (
          <div className="ai-more">
            <Button size="small" icon={<PlusOutlined />} onClick={onAdd}>添加成员</Button>
          </div>
        )}
      </div>
      <div className="ai-card-body">
        {team.length === 0 ? (
          <div className="ai-empty">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有团队成员">
              {canManage && (
                <Button type="primary" icon={<PlusOutlined />} onClick={onAdd}>
                  添加第一个成员
                </Button>
              )}
            </Empty>
          </div>
        ) : (
          <div className="ai-team-grid">
            {team.map(member => (
              <div key={member.id} className={`ai-member ${member.status === 'active' ? '' : 'disabled'}`}>
                <div className="ai-avatar">{(member.name || '?').slice(0, 1)}</div>
                <div className="ai-member-main">
                  <div className="ai-member-title">
                    <span className="ai-member-name">{member.name}</span>
                    <span className="ai-member-meta">{member.agent_no}</span>
                    <span className={`sc-tag ${member.status === 'active' ? 'sc-tag-done' : 'sc-tag-wait'}`}>
                      {member.status === 'active' ? '启用' : '停用'}
                    </span>
                  </div>
                  {member.description && <div className="ai-member-desc">{member.description}</div>}
                  <div className="ai-member-tags">
                    <CapabilityTags items={member.capabilities} max={3} />
                    {(member.skills || []).length > 0 && (
                      <span className="ai-tag-list">
                        {(member.skills || []).slice(0, 2).map(skill => (
                          <span key={skill.id} className="sc-tag sc-tag-purple">{skill.name}</span>
                        ))}
                        {(member.skills || []).length > 2 && (
                          <span className="sc-tag sc-tag-plain">+{(member.skills || []).length - 2}</span>
                        )}
                      </span>
                    )}
                  </div>
                </div>
                {canManage && (
                  <div className="ai-member-action">
                    <Popconfirm
                      title="移除该成员？"
                      description="移除后助手将失去该成员对应的能力。"
                      okText="移除"
                      cancelText="取消"
                      okButtonProps={{ danger: true }}
                      onConfirm={() => onRemove(member.id)}
                    >
                      <Button type="text" size="small" danger>移除</Button>
                    </Popconfirm>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

function TeamCapabilityCard(props: {
  capabilities: Array<{ code: string; name: string }>
  skills: AgentSkillBrief[]
}) {
  const { capabilities, skills } = props
  return (
    <section className="ai-card">
      <div className="ai-card-head">
        <h3>团队能力</h3>
        <span className="ai-hint">{capabilities.length} 项</span>
      </div>
      <div className="ai-card-body">
        {capabilities.length === 0 ? (
          <div className="ai-empty">还没有能力，先添加团队成员</div>
        ) : (
          <span className="ai-tag-list">
            {capabilities.map(capability => (
              <span key={capability.code} className="sc-tag sc-tag-kit">{capability.name}</span>
            ))}
          </span>
        )}
        <div style={{ marginTop: 16 }}>
          <div className="ai-card-head" style={{ padding: 0, borderBottom: 'none' }}>
            <h3>团队技能</h3>
            <span className="ai-hint">{skills.length} 个</span>
          </div>
          <div style={{ marginTop: 8 }}>
            {skills.length === 0 ? (
              <span className="ai-muted">暂无技能</span>
            ) : (
              <span className="ai-tag-list">
                {skills.map(skill => (
                  <span key={`${skill.id}-${skill.name}`} className="sc-tag sc-tag-purple">
                    {skill.name}
                    {(skill as any).agent_name ? ` · ${(skill as any).agent_name}` : ''}
                  </span>
                ))}
              </span>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}

function RecentConversationsCard(props: {
  conversations: ConversationItem[]
  onNew: () => void
  onContinue: (id: number) => void
  onView: (id: number) => void
}) {
  const { conversations, onNew, onContinue, onView } = props
  return (
    <section className="ai-card">
      <div className="ai-card-head">
        <h3>最近会话</h3>
        <div className="ai-more">
          <Button size="small" onClick={onNew}>新建对话</Button>
        </div>
      </div>
      <div className="ai-card-body" style={{ paddingTop: 6, paddingBottom: 6 }}>
        {conversations.length === 0 ? (
          <div className="ai-empty">暂无会话</div>
        ) : (
          <div className="ai-list">
            {conversations.slice(0, 6).map(conversation => (
              <div key={conversation.id} className="ai-list-row">
                <div className="ai-list-main">
                  <div className="ai-list-title">{conversation.title || `会话 #${conversation.id}`}</div>
                  <div className="ai-list-sub">{formatTime(conversation.last_message_at)}</div>
                </div>
                <div className="ai-list-actions">
                  <Button type="link" size="small" onClick={() => onContinue(conversation.id)}>继续</Button>
                  <Button type="link" size="small" onClick={() => onView(conversation.id)}>查看</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

function RecentCallsCard({ calls }: { calls: AgentCall[] }) {
  return (
    <section className="ai-card">
      <div className="ai-card-head">
        <h3>最近调用</h3>
        <span className="ai-hint">最近 {calls.length} 次</span>
      </div>
      <div className="ai-card-body flush">
        <Table
          size="small"
          rowKey="id"
          pagination={false}
          dataSource={calls.slice(0, 5)}
          locale={{ emptyText: <div className="ai-empty">暂无调用</div> }}
          columns={[
            {
              title: '成员', dataIndex: 'callee', width: 110, ellipsis: true,
              render: (callee: AgentCall['callee']) => callee?.name || '-',
            },
            { title: '能力', dataIndex: 'capability', width: 120, ellipsis: true },
            {
              title: '状态', dataIndex: 'status', width: 82,
              render: (value: string) => {
                const meta = CALL_STATUS_META[value] || { cls: 'sc-tag-plain', text: value }
                return <span className={`sc-tag ${meta.cls}`}>{meta.text}</span>
              },
            },
            {
              title: '结果', dataIndex: 'result_summary', ellipsis: true,
              render: (value: string | null, row: AgentCall) => value || row.error || '-',
            },
            { title: '时间', dataIndex: 'created_at', width: 108, render: formatTime },
          ]}
        />
      </div>
    </section>
  )
}

export default function MyAssistant() {
  const navigate = useNavigate()
  const hasPermission = useAuthStore((s: any) => s.hasPermission) as (resource: string, action: string) => boolean
  const canManageTeam = hasPermission('ai.agent.assistant', 'read')

  const [me, setMe] = useState<any>(null)
  const [team, setTeam] = useState<TeamMember[]>([])
  const [conversations, setConversations] = useState<ConversationItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [addOpen, setAddOpen] = useState(false)
  const [conversationOpen, setConversationOpen] = useState(false)
  const [conversationDetail, setConversationDetail] = useState<any>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [meRes, teamRes, conversationRes]: any = await Promise.all([
        agentApi.me(),
        agentApi.team().catch(() => ({ data: { items: [] } })),
        agentApi.conversations({ page_size: 50 }, true).catch(() => ({ data: { items: [] } })),
      ])
      setMe(meRes.data)
      setTeam(teamRes.data?.items || [])
      setConversations(conversationRes.data?.items || [])
    } catch (e: any) {
      setError(e?._apiData?.message || e?.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const newConversation = () => {
    navigate('/ai-assistant', { state: { newConversation: true } })
  }

  const openConversation = (id: number) => {
    navigate('/ai-assistant', { state: { conversationId: id } })
  }

  const viewConversation = async (id: number) => {
    const res: any = await agentApi.conversation(id)
    setConversationDetail(res.data)
    setConversationOpen(true)
  }

  const removeMember = async (agentId: number) => {
    await agentApi.removeMember(agentId)
    message.success('已移出团队')
    await load()
  }

  if (error) {
    return (
      <div className="sc-page ai-center ai-page">
        <div className="ai-card">
          <div className="ai-empty">
            <Empty description={error}>
              <Button onClick={load}>重试</Button>
            </Empty>
          </div>
        </div>
      </div>
    )
  }

  if (!me && loading) {
    return (
      <div className="sc-page ai-center ai-page">
        <div className="ai-card"><div className="ai-empty"><Spin /></div></div>
      </div>
    )
  }

  const skills: AgentSkillBrief[] = me?.skills || []
  const calls: AgentCall[] = me?.recent_calls || []
  const capabilities: Array<{ code: string; name: string }> = me?.effective_capabilities || []

  return (
    <div className="sc-page ai-center ai-page">
      <PageHeader
        title="我的助手"
        subtitle="你的团队能力决定助手能做什么"
        extra={(
          <Space>
            <Button icon={<MessageOutlined />} onClick={() => navigate('/ai-assistant')}>打开助手</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={newConversation}>新建对话</Button>
          </Space>
        )}
      />

      <div className="ai-stat-grid">
        <StatCard icon={<TeamOutlined />} label="团队成员" value={me?.team_size || 0} unit="位" />
        <StatCard icon={<MessageOutlined />} label="近 7 天对话" value={formatNumber(me?.usage_7d?.runs || 0)} unit="次" accent="#0284c7" accentBg="#f0f9ff" />
        <StatCard icon={<ThunderboltOutlined />} label="近 7 天 Token" value={formatNumber(me?.usage_7d?.total_tokens || 0)} accent="#8b5cf6" accentBg="#f5f3ff" />
        <StatCard icon={<HistoryOutlined />} label="最近调用" value={calls.length} unit="次" accent="#d97706" accentBg="#fffbeb" />
      </div>

      <div className="ai-two-col">
        <TeamMembersCard
          team={team}
          canManage={canManageTeam}
          onAdd={() => setAddOpen(true)}
          onRemove={removeMember}
        />
        <TeamCapabilityCard capabilities={capabilities} skills={skills} />
      </div>

      <div className="ai-two-col reverse">
        <RecentConversationsCard
          conversations={conversations}
          onNew={newConversation}
          onContinue={openConversation}
          onView={viewConversation}
        />
        <RecentCallsCard calls={calls} />
      </div>

      <AddMemberDrawer
        open={addOpen}
        existingIds={team.map(member => member.id)}
        onClose={() => setAddOpen(false)}
        onAdded={load}
      />

      <Drawer
        title={conversationDetail?.title || '会话内容'}
        width={560}
        open={conversationOpen}
        onClose={() => setConversationOpen(false)}
        className="sc-page"
      >
        <List
          dataSource={conversationDetail?.messages || []}
          locale={{ emptyText: '暂无消息' }}
          renderItem={(item: any) => (
            <List.Item style={{ display: 'block' }}>
              <div className="ai-list-sub" style={{ marginBottom: 4 }}>
                {item.role === 'user' ? '我' : '助手'} · {item.created_at ? formatTime(item.created_at) : ''}
              </div>
              {item.role === 'assistant'
                ? <Markdown>{item.content || ''}</Markdown>
                : <div style={{ whiteSpace: 'pre-wrap' }}>{item.content}</div>}
            </List.Item>
          )}
        />
      </Drawer>
    </div>
  )
}
