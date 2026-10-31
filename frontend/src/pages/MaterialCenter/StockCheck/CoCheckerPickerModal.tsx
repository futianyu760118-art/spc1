import { useEffect, useMemo, useState } from 'react'
import { Modal, Input, Checkbox, Button, Space, Spin, Empty, Tag } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import { materialApi } from '@/services/api'

interface Candidate {
  user_id: number
  name: string
  org_name: string
  position_name?: string | null
}

interface Props {
  open: boolean
  initialIds?: number[]
  onCancel: () => void
  onSave: (userIds: number[]) => void
  saveLoading?: boolean
}

export default function CoCheckerPickerModal({ open, initialIds, onCancel, onSave, saveLoading }: Props) {
  const [all, setAll] = useState<Candidate[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [keyword, setKeyword] = useState('')
  const [collapsedOrgs, setCollapsedOrgs] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (!open) return
    setSelected(new Set(initialIds || []))
    setKeyword('')
    setCollapsedOrgs(new Set())
    let cancelled = false
    setLoading(true)
    materialApi
      .getCoCheckerCandidates()
      .then((res: any) => { if (!cancelled) setAll((res?.data || []) as Candidate[]) })
      .catch(() => { if (!cancelled) setAll([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [open, initialIds])

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    if (!kw) return all
    return all.filter((c) =>
      c.name.toLowerCase().includes(kw) ||
      String(c.user_id) === kw ||
      (c.position_name || '').toLowerCase().includes(kw) ||
      (c.org_name || '').toLowerCase().includes(kw),
    )
  }, [all, keyword])

  const grouped = useMemo(() => {
    const m = new Map<string, Candidate[]>()
    for (const c of filtered) {
      (m.get(c.org_name) || m.set(c.org_name, []).get(c.org_name)!)!.push(c)
    }
 return Array.from(m.entries())
  }, [filtered])

  const toggle = (uid: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(uid)) next.delete(uid)
      else next.add(uid)
      return next
    })
  }

  const toggleOrg = (org: string, members: Candidate[]) => {
    const allIn = members.every((m) => selected.has(m.user_id))
    setSelected((prev) => {
      const next = new Set(prev)
      members.forEach((m) => { allIn ? next.delete(m.user_id) : next.add(m.user_id) })
      return next
    })
  }

  const handleSave = () => onSave(Array.from(selected))

  return (
    <Modal
      title="选择共同盘点人员（按组织架构）"
      open={open}
      onCancel={onCancel}
      width={680}
      destroyOnClose
      footer={
        <Space>
          <Button onClick={onCancel}>取消</Button>
          <Button onClick={() => setSelected(new Set())}>清空</Button>
          <Button type="primary" loading={saveLoading} onClick={handleSave}>
            确定（已选 {selected.size} 人）
          </Button>
        </Space>
      }
    >
      <Input
        allowClear
        prefix={<SearchOutlined />}
        placeholder="搜索姓名/岗位/组织"
        value={keyword}
        onChange={(e) => setKeyword(e.target.value)}
        style={{ marginBottom: 12 }}
      />
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
      ) : grouped.length === 0 ? (
        <Empty description="无匹配人员" />
      ) : (
        <div style={{ maxHeight: 460, overflowY: 'auto', border: '1px solid #f0f0f0', borderRadius: 6 }}>
          {grouped.map(([org, members]) => {
            const inCount = members.filter((m) => selected.has(m.user_id)).length
            const isCollapsed = collapsedOrgs.has(org)
            return (
              <div key={org} style={{ borderBottom: '1px solid #f0f0f0' }}>
                <div
                  style={{ padding: '8px 12px', background: '#fafafa', cursor: 'pointer', userSelect: 'none', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                  onClick={() => setCollapsedOrgs((prev) => { const n = new Set(prev); n.has(org) ? n.delete(org) : n.add(org); return n })}
                >
                  <Space>
                    <strong>{isCollapsed ? '▶' : '▼'} {org}</strong>
                    <span style={{ color: '#64748b', fontSize: 12 }}>{members.length} 人</span>
                  </Space>
                  <a style={{ fontSize: 12 }} onClick={(e) => { e.stopPropagation(); toggleOrg(org, members) }}>
                    {inCount === members.length ? '取消全选' : '全选'}
                  </a>
                </div>
                {!isCollapsed && (
                  <div style={{ padding: '4px 12px 8px 24px' }}>
                    {members.map((m) => (
                      <label key={m.user_id} style={{ display: 'flex', alignItems: 'center', padding: '4px 0', cursor: 'pointer' }}>
                        <Checkbox
                          checked={selected.has(m.user_id)}
                          onChange={() => toggle(m.user_id)}
                          style={{ marginRight: 8 }}
                        />
                        <span>{m.name}</span>
                        {m.position_name && <Tag style={{ marginLeft: 8 }}>{m.position_name}</Tag>}
                        <span style={{ color: '#94a3b8', fontSize: 12, marginLeft: 8 }}>#{m.user_id}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </Modal>
  )
}
