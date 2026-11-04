import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Drawer, Empty, Spin, message } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import { agentApi, AgentCapabilityItem } from '../../../services/agent'

interface Candidate {
  id: number
  agent_no: string
  name: string
  capabilities: AgentCapabilityItem[]
  description?: string | null
}

interface Props {
  open: boolean
  existingIds: number[]
  coveredCodes?: string[]
  onClose: () => void
  onAdded: () => void
}

function toneClass(id: number): string {
  return `ac-tone-${(id + 4) % 6}`
}

export default function AddMemberDrawer({
  open, existingIds, coveredCodes = [], onClose, onAdded,
}: Props) {
  const [keyword, setKeyword] = useState('')
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [selectedIds, setSelectedIds] = useState<number[]>([])

  const load = useCallback(async (value: string) => {
    setLoading(true)
    try {
      const res: any = await agentApi.candidates(value)
      setCandidates(res.data?.items || [])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!open) return
    setKeyword('')
    setSelectedIds([])
    load('')
  }, [open, load])

  useEffect(() => {
    if (!open || !keyword) return
    const timer = setTimeout(() => load(keyword), 250)
    return () => clearTimeout(timer)
  }, [open, keyword, load])

  const visible = candidates.filter(item => !existingIds.includes(item.id))

  const newCapabilityCount = useMemo(() => {
    const covered = new Set(coveredCodes)
    const discovered = new Set<string>()
    visible
      .filter(item => selectedIds.includes(item.id))
      .forEach(item => (item.capabilities || []).forEach(capability => {
        if (!covered.has(capability.code)) discovered.add(capability.code)
      }))
    return discovered.size
  }, [visible, selectedIds, coveredCodes])

  const toggle = (id: number) => {
    setSelectedIds(current => (
      current.includes(id) ? current.filter(item => item !== id) : [...current, id]
    ))
  }

  const addSelected = async () => {
    if (selectedIds.length === 0) return
    setSaving(true)
    try {
      for (const agentId of selectedIds) {
        await agentApi.addMember(agentId)
      }
      message.success(`已加入 ${selectedIds.length} 位成员`)
      setSelectedIds([])
      onAdded()
      onClose()
      await load(keyword)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Drawer
      title={(
        <div>
          <div className="ac-drawer-title">添加团队成员</div>
          <div className="ac-drawer-sub">选择智能体加入你的团队。加入后，它提供的能力立即对助手生效。</div>
        </div>
      )}
      width={440}
      open={open}
      onClose={onClose}
      destroyOnClose
      className="sc-page ai-center"
      footer={(
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="ac-hint" style={{ marginRight: 'auto' }}>
            {selectedIds.length > 0 ? `已选 ${selectedIds.length} 位` : '成员的并集 = 助手能力'}
          </span>
          <Button onClick={onClose}>取消</Button>
          <Button
            type="primary"
            loading={saving}
            disabled={selectedIds.length === 0}
            onClick={addSelected}
          >
            加入团队
          </Button>
        </div>
      )}
    >
      <label className="ac-search" style={{ marginBottom: 12 }}>
        <SearchOutlined />
        <input
          value={keyword}
          placeholder="搜索智能体名称 / 编号"
          onChange={event => setKeyword(event.target.value)}
          onKeyDown={event => { if (event.key === 'Enter') load(keyword) }}
        />
      </label>

      {loading ? (
        <div className="ac-empty"><Spin /></div>
      ) : visible.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有可添加的智能体" />
      ) : (
        <div>
          {visible.map(item => {
            const selected = selectedIds.includes(item.id)
            return (
              <label
                key={item.id}
                style={{
                  display: 'flex',
                  gap: 10,
                  alignItems: 'flex-start',
                  padding: '9px 8px',
                  marginBottom: 4,
                  border: `1px solid ${selected ? 'var(--ac-brand-line)' : 'var(--ac-line-2)'}`,
                  borderRadius: 4,
                  background: selected ? 'var(--ac-brand-soft)' : '#fff',
                  cursor: 'pointer',
                }}
              >
                <input
                  type="checkbox"
                  checked={selected}
                  onChange={() => toggle(item.id)}
                  style={{ marginTop: 10, accentColor: 'var(--ac-brand)' }}
                />
                <span className={`ac-mono sm ${toneClass(item.id)}`} aria-hidden="true">
                  {(item.name || '?').slice(0, 1)}
                </span>
                <span style={{ minWidth: 0, flex: 1 }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <b style={{ fontSize: 12, color: 'var(--ac-ink)' }}>{item.name}</b>
                    <span className="ac-hint" style={{ fontFamily: 'var(--ac-font-mono)', fontSize: 9 }}>
                      {item.agent_no}
                    </span>
                  </span>
                  {item.description && (
                    <span className="ac-hint" style={{ display: 'block', marginTop: 2, lineHeight: 1.5 }}>
                      {item.description}
                    </span>
                  )}
                  <span className="ac-team-caps">
                    {(item.capabilities || []).slice(0, 3).map(capability => (
                      <span key={capability.code}>{capability.name}</span>
                    ))}
                    {(item.capabilities || []).length > 3 && (
                      <span className="more">+{(item.capabilities || []).length - 3}</span>
                    )}
                  </span>
                </span>
              </label>
            )
          })}
        </div>
      )}

      {newCapabilityCount > 0 && (
        <div className="ac-audit-note" style={{ marginTop: 14 }}>
          <span>加入后可为助手补上 {newCapabilityCount} 项当前未覆盖的能力。</span>
        </div>
      )}
    </Drawer>
  )
}
