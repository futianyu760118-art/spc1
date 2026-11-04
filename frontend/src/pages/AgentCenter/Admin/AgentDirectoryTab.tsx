import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Empty, Spin, message } from 'antd'
import {
  ArrowLeftOutlined, ArrowRightOutlined, EditOutlined,
  PlusOutlined, SearchOutlined, TeamOutlined,
} from '@ant-design/icons'
import { agentApi, AgentInfo } from '../../../services/agent'
import AgentEditDrawer from './AgentEditDrawer'

const PAGE_SIZE = 8

const STATUS_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'active', label: '启用' },
  { value: 'disabled', label: '停用' },
]

interface Props {
  stats: any
  canManage: boolean
  createSignal: number
  onCreateConsumed: () => void
  onBindUsers: (agentIds: number[]) => void
  onChanged: () => void
  onOpenOps: () => void
}

function toneClass(id: number): string {
  return `ac-tone-${(id + 4) % 6}`
}

function categoryOf(code: string): 'query' | 'reason' | 'write' {
  const prefix = code.split('.')[0]
  if (prefix === 'reason' || prefix === 'write') return prefix
  return 'query'
}

const CATEGORY_LABELS: Record<string, string> = {
  query: '查',
  reason: '推',
  write: '写',
}

function formatDate(value?: string): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

export default function AgentDirectoryTab({
  stats, canManage, createSignal, onCreateConsumed, onBindUsers, onChanged, onOpenOps,
}: Props) {
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [keywordInput, setKeywordInput] = useState('')
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [editingAgent, setEditingAgent] = useState<AgentInfo | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await agentApi.adminAgents({
        keyword, status, page, page_size: PAGE_SIZE,
      })
      const items: AgentInfo[] = res.data?.items || []
      setAgents(items)
      setTotal(Number(res.data?.total || 0))
      setSelectedId(current => (
        items.some(item => item.id === current) ? current : (items[0]?.id ?? null)
      ))
    } finally {
      setLoading(false)
    }
  }, [keyword, status, page])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const timer = setTimeout(() => {
      setKeyword(keywordInput.trim())
      setPage(1)
    }, 250)
    return () => clearTimeout(timer)
  }, [keywordInput])

  useEffect(() => {
    if (createSignal > 0) {
      setEditingAgent(null)
      setEditOpen(true)
      onCreateConsumed()
    }
  }, [createSignal, onCreateConsumed])

  const selected = agents.find(item => item.id === selectedId) || null
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const activeCount = Number(stats?.active_agents ?? 0)
  const totalAgents = Number(stats?.agents ?? total)
  const disabledCount = Math.max(0, totalAgents - activeCount)

  const openEdit = (agent: AgentInfo) => {
    setEditingAgent(agent)
    setEditOpen(true)
  }

  const enableAgent = async (agent: AgentInfo) => {
    await agentApi.updateAgent(agent.id, {
      name: agent.name,
      capabilities: (agent.capabilities || []).map(item => item.code),
      skill_ids: (agent.skills || []).map(item => item.id),
      scope_type: agent.scope_type || 'all',
      scope_role_ids: agent.scope_type === 'roles' ? (agent.scope_role_ids || []) : null,
      description: agent.description || null,
      status: 'active',
    })
    message.success('已启用')
    await load()
    onChanged()
  }

  const capabilities = selected?.capabilities || []
  const skills = selected?.skills || []
  const scopeLabel = selected?.scope_type === 'roles'
    ? `指定角色 × ${selected.scope_role_ids?.length || 0}`
    : '所有人可勾选'

  const listContent = useMemo(() => {
    if (loading && agents.length === 0) {
      return <div className="ac-empty"><Spin /></div>
    }
    if (agents.length === 0) {
      return (
        <div className="ac-empty">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的智能体" />
        </div>
      )
    }
    return (
      <ul className="ac-agent-list" role="list">
        {agents.map(agent => (
          <li
            key={agent.id}
            role="button"
            tabIndex={0}
            className={`ac-agent-row ${agent.id === selectedId ? 'active' : ''}`}
            onClick={() => setSelectedId(agent.id)}
            onKeyDown={event => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                setSelectedId(agent.id)
              }
            }}
          >
            <span className={`ac-mono ${agent.status === 'active' ? toneClass(agent.id) : 'ac-tone-off'}`}>
              {(agent.name || '?').slice(0, 1)}
            </span>
            <span className="ac-agent-row-main">
              <span className="ac-agent-row-name">{agent.name}</span>
              <span className="ac-agent-row-code">
                {agent.agent_no} · {(agent.capabilities || []).length} 能力
              </span>
            </span>
            <span
              className={`ac-dot ${agent.status === 'active' ? 'on' : 'off'}`}
              title={agent.status === 'active' ? '启用' : '停用'}
            />
          </li>
        ))}
      </ul>
    )
  }, [agents, loading, selectedId])

  return (
    <div className="ac-catalog">
      <aside className="ac-surface ac-index" aria-label="智能体目录">
        <div className="ac-index-toolbar">
          <label className="ac-search">
            <SearchOutlined />
            <input
              value={keywordInput}
              placeholder="搜索名称 / 编号"
              onChange={event => setKeywordInput(event.target.value)}
            />
          </label>
          <div className="ac-chips">
            {STATUS_OPTIONS.map(option => {
              const count = option.value === 'active'
                ? activeCount
                : option.value === 'disabled' ? disabledCount : totalAgents
              return (
                <button
                  key={option.value}
                  type="button"
                  className={`ac-chip ${status === option.value ? 'active' : ''}`}
                  onClick={() => { setStatus(option.value); setPage(1) }}
                >
                  {option.label} {count}
                </button>
              )
            })}
          </div>
        </div>

        {listContent}

        <div className="ac-index-foot">
          <span>共 {total} 个 · 第 {page} / {totalPages} 页</span>
          <div className="ac-pager">
            <button
              type="button"
              disabled={page <= 1}
              aria-label="上一页"
              onClick={() => setPage(current => Math.max(1, current - 1))}
            >
              <ArrowLeftOutlined />
            </button>
            <button
              type="button"
              disabled={page >= totalPages}
              aria-label="下一页"
              onClick={() => setPage(current => Math.min(totalPages, current + 1))}
            >
              <ArrowRightOutlined />
            </button>
          </div>
        </div>
      </aside>

      {!selected ? (
        <section className="ac-surface ac-agent-sheet">
          <div className="ac-empty" style={{ paddingTop: 80 }}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={keyword || status ? '没有匹配的智能体' : '还没有智能体'}
            >
              {canManage && !keyword && !status && (
                <button type="button" className="ac-btn primary" onClick={() => { setEditingAgent(null); setEditOpen(true) }}>
                  <PlusOutlined /> 新建第一个智能体
                </button>
              )}
            </Empty>
          </div>
        </section>
      ) : (
        <section className="ac-surface ac-agent-sheet" aria-live="polite">
          <div className="ac-sheet-head">
            <div className={`ac-mono lg ${selected.status === 'active' ? toneClass(selected.id) : 'ac-tone-off'}`} aria-hidden="true">
              {(selected.name || '?').slice(0, 1)}
            </div>
            <div className="ac-sheet-title">
              <div className="ac-sheet-kicker">智能体剖面 · {selected.agent_no}</div>
              <h2>
                {selected.name}
                <span className={`ac-status ${selected.status === 'active' ? '' : 'off'}`}>
                  {selected.status === 'active' ? '启用' : '停用'}
                </span>
              </h2>
              <p>{selected.description || '暂无说明'}</p>
            </div>
            {canManage && (
              <div className="ac-sheet-actions">
                {selected.status === 'disabled' ? (
                  <button type="button" className="ac-btn primary" onClick={() => enableAgent(selected)}>
                    启用智能体
                  </button>
                ) : (
                  <button type="button" className="ac-btn" onClick={() => onBindUsers([selected.id])}>
                    <TeamOutlined /> 绑定用户
                  </button>
                )}
                <button type="button" className="ac-btn" onClick={() => openEdit(selected)}>
                  <EditOutlined /> 编辑
                </button>
              </div>
            )}
          </div>

          <div className="ac-sheet-metrics">
            <div><b>{capabilities.length}</b><span>能力</span></div>
            <div><b>{skills.length}</b><span>技能</span></div>
            <div><b>{selected.teams_count || 0}</b><span>团队引用</span></div>
            <div><b style={{ fontSize: 15 }}>{scopeLabel}</b><span>开放范围</span></div>
          </div>

          <div className="ac-sheet-body">
            <div className="ac-sheet-cols">
              <section>
                <h3>能力 <span className="ac-hint">{capabilities.length} 项 · 按类别</span></h3>
                {capabilities.length === 0 ? (
                  <div className="ac-empty">还没有配置能力</div>
                ) : (
                  <div className="ac-cap-tiles">
                    {capabilities.map(capability => {
                      const category = categoryOf(capability.code)
                      return (
                        <div className="ac-cap-tile" key={capability.code}>
                          <b>
                            <span className={`ac-cat ${category}`}>{CATEGORY_LABELS[category]}</span>
                            {capability.name}
                          </b>
                          <small>{capability.code}</small>
                        </div>
                      )
                    })}
                  </div>
                )}
              </section>

              <section>
                <h3>技能 <span className="ac-hint">{skills.length} 个已绑定</span></h3>
                {skills.length === 0 ? (
                  <div className="ac-empty" style={{ padding: '12px 0' }}>未绑定技能</div>
                ) : (
                  skills.map(skill => (
                    <div className="ac-skill-line" key={skill.id}>
                      <span className="ac-skill-ico">SK</span>
                      <span className="ac-skill-line-main">
                        <b>{skill.name}</b>
                        <small>{skill.skill_key || `skill-${skill.id}`} · {skill.description || '—'}</small>
                      </span>
                      <span className={`ac-status ${skill.status === 'active' ? '' : 'off'}`}>
                        {skill.status === 'active' ? '启用' : '停用'}
                      </span>
                    </div>
                  ))
                )}
              </section>
            </div>

            <section className="ac-scope-block">
              <h3>开放范围与绑定</h3>
              <div className="ac-scope-grid">
                <div><span>勾选范围</span><b>{selected.scope_type === 'roles' ? '指定角色' : '所有人可勾选'}</b></div>
                <div><span>指定角色</span><b>{selected.scope_type === 'roles' ? `${selected.scope_role_ids?.length || 0} 个` : '—'}</b></div>
                <div>
                  <span>绑定用户</span>
                  <b>—</b>
                  {canManage && (
                    <button type="button" className="ac-link" onClick={() => onBindUsers([selected.id])}>查看</button>
                  )}
                </div>
                <div><span>被团队引用</span><b>{selected.teams_count || 0} 个团队</b></div>
              </div>
            </section>

            <div className="ac-activity-strip">
              <span className="label">运营数据</span>
              <span className="stat">创建于 {formatDate(selected.created_at)}</span>
              <span className="stat" style={{ marginLeft: 'auto' }}>调用明细见助手运营 · 调用审计</span>
              <button type="button" className="ac-btn small" onClick={onOpenOps}>查看运营</button>
            </div>
          </div>
        </section>
      )}

      <AgentEditDrawer
        open={editOpen}
        agent={editingAgent}
        onClose={() => setEditOpen(false)}
        onSaved={() => { load(); onChanged() }}
      />
    </div>
  )
}
