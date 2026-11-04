import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Button, Drawer, Empty, List, Popconfirm, Spin, message,
} from 'antd'
import {
  MessageOutlined, PlusOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import {
  agentApi, AgentCall, AgentCapabilityItem, TeamMember,
} from '../../../services/agent'
import PageHeader from '../../../components/Agent/PageHeader'
import Markdown from '../../../components/Markdown'
import { useAuthStore } from '../../../store/auth'
import AddMemberDrawer from './AddMemberDrawer'
import '../agent-center.css'
import '../agent-center-v3.css'

interface ConversationItem {
  id: number
  title?: string
  status?: string
  last_message_at?: string
}

interface CatalogCapability {
  code: string
  name: string
  category: string
  grantable?: boolean
}

interface MeData {
  team_size: number
  usage_7d?: { runs: number; total_tokens: number }
  effective_capabilities?: AgentCapabilityItem[]
  skills?: Array<{
    id: number
    name: string
    description?: string
    agent_id?: number
    agent_name?: string
  }>
  capability_catalog?: CatalogCapability[]
  recent_calls?: AgentCall[]
}

const CATEGORY_ORDER = ['query', 'reason', 'write']

const CALL_STATUS_META: Record<string, { cls: string; text: string }> = {
  success: { cls: 'ok', text: '成功' },
  completed: { cls: 'ok', text: '成功' },
  done: { cls: 'ok', text: '成功' },
  failed: { cls: 'bad', text: '失败' },
  timeout: { cls: 'bad', text: '超时' },
  rejected: { cls: 'bad', text: '拒绝' },
  running: { cls: '', text: '进行中' },
  cancelled: { cls: '', text: '已取消' },
}

function formatNumber(value: number): string {
  return value.toLocaleString('zh-CN')
}

function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`
  return String(value)
}

function formatTime(value?: string): string {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

function timeParts(value?: string): { date: string; time: string } {
  if (!value) return { date: '--/--', time: '--:--' }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return { date: '--/--', time: '--:--' }
  return {
    date: date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }),
    time: date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
  }
}

function toneClass(id: number): string {
  return `ac-tone-${(id + 4) % 6}`
}

function capabilityCategory(code: string): string {
  const prefix = code.split('.')[0]
  return CATEGORY_ORDER.includes(prefix) ? prefix : 'other'
}

function callCapabilityLabel(code: string, catalogNames: Map<string, string>): string {
  const known = catalogNames.get(code)
  if (known) return known
  if (code.includes(':')) {
    const tail = code.split(':').pop() || code
    return tail.split('/').pop() || tail
  }
  return code
}

function formatDuration(value?: number | null): string {
  if (value == null) return '-'
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`
  return `${Math.round(value)}ms`
}

export default function MyAssistant() {
  const navigate = useNavigate()
  const hasPermission = useAuthStore((s: any) => s.hasPermission) as (resource: string, action: string) => boolean
  const canManageTeam = hasPermission('ai.agent.assistant', 'read')

  const [me, setMe] = useState<MeData | null>(null)
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

  const catalog = useMemo<CatalogCapability[]>(() => {
    const raw = (me?.capability_catalog || [])
      .filter(item => item.grantable !== false && CATEGORY_ORDER.includes(item.category))
      .map(item => ({ ...item }))

    if (raw.length > 0) {
      return raw.sort((a, b) => {
        const order = CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category)
        return order !== 0 ? order : a.name.localeCompare(b.name, 'zh-CN')
      })
    }

    const fallback = new Map<string, CatalogCapability>()
    const add = (item: AgentCapabilityItem) => {
      if (!fallback.has(item.code)) {
        fallback.set(item.code, {
          code: item.code,
          name: item.name,
          category: capabilityCategory(item.code),
        })
      }
    }
    ;(me?.effective_capabilities || []).forEach(add)
    team.forEach(member => (member.capabilities || []).forEach(add))
    return Array.from(fallback.values())
      .filter(item => CATEGORY_ORDER.includes(item.category))
      .sort((a, b) => {
        const order = CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category)
        return order !== 0 ? order : a.name.localeCompare(b.name, 'zh-CN')
      })
  }, [me, team])

  const catalogNames = useMemo(
    () => new Map(catalog.map(item => [item.code, item.name])),
    [catalog],
  )

  const coverage = useMemo(() => {
    const result = new Map<string, number>()
    team.forEach((member, index) => {
      if (member.status !== 'active') return
      ;(member.capabilities || []).forEach(capability => {
        if (!result.has(capability.code)) result.set(capability.code, index)
      })
    })
    return result
  }, [team])

  const coveredCount = useMemo(
    () => catalog.filter(item => coverage.has(item.code)).length,
    [catalog, coverage],
  )

  const skills = me?.skills || []
  const calls = me?.recent_calls || []
  const usages = me?.usage_7d || { runs: 0, total_tokens: 0 }

  if (error) {
    return (
      <div className="sc-page ai-center ai-page ac-page">
        <PageHeader
          title="我的助手"
          extra={(
            <Button type="primary" icon={<PlusOutlined />} onClick={newConversation}>
              新建对话
            </Button>
          )}
        />
        <div className="ac-surface">
          <div className="ac-empty">
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
      <div className="sc-page ai-center ai-page ac-page">
        <PageHeader title="我的助手" />
        <div className="ac-surface"><div className="ac-empty"><Spin /></div></div>
      </div>
    )
  }

  return (
    <div className="sc-page ai-center ai-page ac-page">
      <PageHeader
        title="我的助手"
        extra={(
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="ac-btn" onClick={() => navigate('/ai-assistant')}>
              <MessageOutlined /> 打开助手
            </button>
            <button type="button" className="ac-btn primary" onClick={newConversation}>
              <PlusOutlined /> 新建对话
            </button>
          </div>
        )}
      />

      <div className="ac-stat-strip">
        <div className="ac-stat"><b>{team.length}</b><span>团队成员</span></div>
        <div className="ac-stat"><b>{coveredCount}</b><span>覆盖能力</span></div>
        <div className="ac-stat"><b>{skills.length}</b><span>已绑定技能</span></div>
        <div className="ac-stat"><b>{formatNumber(usages.runs)}</b><span>近 7 天对话</span></div>
        <div className="ac-stat"><b>{formatTokens(usages.total_tokens)}</b><span>近 7 天 Token</span></div>
        <div className="ac-stat-note"><i className="ac-live-dot" />团队能力实时生效</div>
      </div>

      <section className="ac-surface" aria-labelledby="teamTitle">
        <div className="ac-surface-head">
          <h2 id="teamTitle">团队编组</h2>
          <span className="ac-hint">成员的并集决定助手能力；移除成员会立即收回对应能力</span>
          <div className="ac-actions">
            {canManageTeam && (
              <button type="button" className="ac-btn small" onClick={() => setAddOpen(true)}>
                <PlusOutlined /> 添加成员
              </button>
            )}
          </div>
        </div>
        <div className="ac-team-grid">
          {team.map(member => (
            <article className="ac-team-cell" key={member.id}>
              <div className={`ac-mono ${member.status === 'active' ? toneClass(member.id) : 'ac-tone-off'}`} aria-hidden="true">
                {(member.name || '?').slice(0, 1)}
              </div>
              <div className="ac-team-main">
                <div className="ac-team-name">
                  <span className="name">{member.name}</span>
                  <span className={`ac-status ${member.status === 'active' ? '' : 'off'}`}>
                    {member.status === 'active' ? '启用' : '停用'}
                  </span>
                </div>
                <div className="ac-team-code">{member.agent_no}</div>
                {member.description && <div className="ac-team-desc">{member.description}</div>}
                <div className="ac-team-caps">
                  {(member.capabilities || []).slice(0, 3).map(capability => (
                    <span key={capability.code}>{capability.name}</span>
                  ))}
                  {(member.capabilities || []).length > 3 && (
                    <span className="more">+{(member.capabilities || []).length - 3}</span>
                  )}
                  {(member.capabilities || []).length === 0 && (
                    <span className="more">未配置能力</span>
                  )}
                </div>
              </div>
              {canManageTeam && (
                <Popconfirm
                  title="移除该成员？"
                  description="移除后助手将失去该成员对应的能力。"
                  okText="移除"
                  cancelText="取消"
                  okButtonProps={{ danger: true }}
                  onConfirm={() => removeMember(member.id)}
                >
                  <button type="button" className="ac-remove" aria-label="移除成员">×</button>
                </Popconfirm>
              )}
            </article>
          ))}
          {team.length === 0 && (
            <div className="ac-empty" style={{ gridColumn: '1 / -1' }}>
              还没有团队成员
              {canManageTeam && (
                <div style={{ marginTop: 10 }}>
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
                    添加第一个成员
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      <div className="ac-activity-grid">
        <div className="ac-activity-col">
          <section className="ac-surface" aria-labelledby="convTitle">
            <div className="ac-surface-head">
              <h2 id="convTitle">最近会话</h2>
              <div className="ac-actions">
                <button type="button" className="ac-link" onClick={() => navigate('/ai-assistant')}>全部</button>
              </div>
            </div>
            {conversations.length === 0 ? (
              <div className="ac-empty">暂无会话</div>
            ) : (
              <ul className="ac-conv-list">
                {conversations.slice(0, 4).map(conversation => {
                  const time = timeParts(conversation.last_message_at)
                  return (
                    <li
                      className="ac-conv-item"
                      key={conversation.id}
                      onClick={() => openConversation(conversation.id)}
                      title="继续会话"
                    >
                      <div className="ac-conv-date">{time.date}<br />{time.time}</div>
                      <div className="ac-conv-body">
                        <div className="ac-conv-title">{conversation.title || `会话 #${conversation.id}`}</div>
                        <div className="ac-conv-meta">
                          <span className="tag">{conversation.status === 'archived' ? '已归档' : '会话'}</span>
                          <button
                            type="button"
                            className="ac-link"
                            onClick={event => { event.stopPropagation(); viewConversation(conversation.id) }}
                          >
                            查看
                          </button>
                        </div>
                      </div>
                      <span className="ac-conv-go" aria-hidden="true">→</span>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>

          <section className="ac-surface" aria-labelledby="callTitle">
            <div className="ac-surface-head">
              <h2 id="callTitle">最近调用</h2>
              <span className="ac-hint">近 {Math.min(calls.length, 5)} 次</span>
            </div>
            {calls.length === 0 ? (
              <div className="ac-empty">暂无调用</div>
            ) : (
              <table className="ac-mini-table ac-calls-table">
                <thead>
                  <tr><th>成员</th><th>能力</th><th>状态</th><th>耗时</th></tr>
                </thead>
                <tbody>
                  {calls.slice(0, 5).map(call => {
                    const meta = CALL_STATUS_META[call.status] || { cls: '', text: call.status }
                    const memberName = call.callee?.name || '-'
                    const capabilityLabel = callCapabilityLabel(call.capability, catalogNames)
                    return (
                      <tr key={call.id}>
                        <td title={memberName}>{memberName}</td>
                        <td title={call.capability}>{capabilityLabel}</td>
                        <td className={meta.cls}>{meta.text}</td>
                        <td className="mono">{formatDuration(call.duration_ms)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </section>

          {skills.length > 0 && (
            <section className="ac-surface ac-skill-card" aria-labelledby="skillTitle">
              <div className="ac-surface-head">
                <h2 id="skillTitle">已绑定技能</h2>
                <span className="ac-hint">{skills.length} 个</span>
              </div>
              <div className="ac-skill-foot-list">
                {skills.map(skill => (
                  <div className="ac-skill-foot-row" key={`${skill.id}-${skill.name}`}>
                    <span className="sk">SK</span>
                    <span>{skill.name}</span>
                    {skill.agent_name && <span className="an">{skill.agent_name}</span>}
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>

      <AddMemberDrawer
        open={addOpen}
        existingIds={team.map(member => member.id)}
        coveredCodes={Array.from(coverage.keys())}
        onClose={() => setAddOpen(false)}
        onAdded={load}
      />

      <Drawer
        title={conversationDetail?.title || '会话内容'}
        width={560}
        open={conversationOpen}
        onClose={() => setConversationOpen(false)}
        className="sc-page ai-center"
      >
        <List
          dataSource={conversationDetail?.messages || []}
          locale={{ emptyText: '暂无消息' }}
          renderItem={(item: any) => (
            <List.Item style={{ display: 'block' }}>
              <div className="ac-hint" style={{ marginBottom: 4 }}>
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
