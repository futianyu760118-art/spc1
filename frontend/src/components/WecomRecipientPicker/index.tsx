import React, { useEffect, useMemo, useState } from 'react'
import { Tree, Input, Checkbox, Empty, Tag, Space, Spin, Alert } from 'antd'
import { wecomApi, WecomUser, WecomDepartment } from '@/services/api'

export interface WecomRecipientValue {
  user_ids: string[]
}

interface Props {
  value: WecomRecipientValue
  onChange: (v: WecomRecipientValue) => void
  userOptions?: WecomUser[]
  loading?: boolean
  errorMessage?: string | null
}

interface DeptTreeNode {
  key: number
  title: string
  children?: DeptTreeNode[]
}

function buildTree(departments: WecomDepartment[]): DeptTreeNode[] {
  const nodes = new Map<number, DeptTreeNode>()
  departments.forEach(d => {
    nodes.set(d.id, { key: d.id, title: d.name, children: [] })
  })
  const roots: DeptTreeNode[] = []
  departments.forEach(d => {
    const node = nodes.get(d.id)!
    const parent = nodes.get(d.parent_id)
    if (parent) parent.children!.push(node)
    else roots.push(node)
  })
  const clean = (n: DeptTreeNode): DeptTreeNode =>
    n.children && n.children.length ? { ...n, children: n.children.map(clean) } : { key: n.key, title: n.title }
  return roots.map(clean)
}

export const WecomRecipientPicker: React.FC<Props> = ({
  value, onChange, userOptions, loading, errorMessage,
}) => {
  const [keyword, setKeyword] = useState('')
  const [selectedDept, setSelectedDept] = useState<number | null>(null)
  const [internalUsers, setInternalUsers] = useState<WecomUser[]>([])
  const [departments, setDepartments] = useState<WecomDepartment[]>([])
  const [internalLoading, setInternalLoading] = useState(false)
  const [err, setErr] = useState<string | null>(errorMessage ?? null)

  useEffect(() => {
    if (userOptions) return
    setInternalLoading(true)
    wecomApi.listUsers()
      .then((res: any) => setInternalUsers(res?.data || []))
      .catch((e) => setErr(e?.message || '通讯录加载失败'))
      .finally(() => setInternalLoading(false))
  }, [userOptions])

  useEffect(() => {
    wecomApi.listDepartments()
      .then((res: any) => setDepartments(res?.data || []))
      .catch((e) => setErr(e?.message || '部门加载失败'))
  }, [])

  const users = userOptions ?? internalUsers
  const isLoading = loading ?? internalLoading

  const deptTree = useMemo(() => buildTree(departments), [departments])

  const directUsers = useMemo(() => {
    if (selectedDept == null) return users
    return users.filter(u => (u.department || []).includes(selectedDept))
  }, [users, selectedDept])

  const filteredUsers = useMemo(() => {
    if (!keyword) return directUsers
    const k = keyword.toLowerCase()
    return users.filter(u => u.userid.toLowerCase().includes(k) || u.name.toLowerCase().includes(k))
  }, [users, directUsers, keyword])

  const toggle = (id: string) => {
    const cur = new Set(value.user_ids)
    if (cur.has(id)) cur.delete(id)
    else cur.add(id)
    onChange({ ...value, user_ids: Array.from(cur) })
  }

  const selectedChips = useMemo(() => {
    const chips: { id: string; label: string }[] = []
    value.user_ids.forEach(id => {
      const u = users.find(x => x.userid === id)
      chips.push({ id, label: u ? `${u.name} (${u.userid})` : id })
    })
    return chips
  }, [value, users])

  return (
    <div>
      {err && <Alert type="error" message={err} showIcon style={{ marginBottom: 12 }} />}
      <Input.Search
        placeholder="搜索姓名/userid（搜索时忽略部门）"
        value={keyword}
        onChange={e => setKeyword(e.target.value)}
        style={{ marginBottom: 12 }}
      />
      {isLoading ? <Spin /> : (
        <div style={{ display: 'flex', border: '1px solid #f0f0f0', borderRadius: 6, height: 300 }}>
          <div style={{ width: 200, borderRight: '1px solid #f0f0f0', overflow: 'auto', padding: '8px 4px' }}>
            <Tree
              treeData={deptTree}
              defaultExpandAll
              selectedKeys={selectedDept != null ? [selectedDept] : []}
              onSelect={(keys) => setSelectedDept(keys.length ? Number(keys[0]) : null)}
            />
          </div>
          <div style={{ flex: 1, overflow: 'auto', padding: 12 }}>
            {keyword ? (
              <div style={{ marginBottom: 6, color: '#666' }}>搜索结果 ({filteredUsers.length})</div>
            ) : selectedDept != null ? (
              <div style={{ marginBottom: 6, color: '#666' }}>
                {departments.find(d => d.id === selectedDept)?.name ?? ''} ({directUsers.length})
              </div>
            ) : (
              <div style={{ marginBottom: 6, color: '#666' }}>请在左侧选择部门</div>
            )}
            {filteredUsers.length ? (
              <Checkbox.Group style={{ width: '100%' }} value={value.user_ids}>
                {filteredUsers.map(u => (
                  <div key={u.userid} style={{ padding: '4px 0' }}>
                    <Checkbox value={u.userid} onChange={() => toggle(u.userid)}>
                      {u.name} <span style={{ color: '#999' }}>({u.userid})</span>
                    </Checkbox>
                  </div>
                ))}
              </Checkbox.Group>
            ) : !isLoading ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} /> : null}
          </div>
        </div>
      )}
      {selectedChips.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ marginBottom: 6, color: '#666' }}>已选 ({selectedChips.length})</div>
          <Space wrap>
            {selectedChips.map(c => (
              <Tag key={c.id} closable onClose={() => toggle(c.id)}>
                {c.label}
              </Tag>
            ))}
          </Space>
        </div>
      )}
    </div>
  )
}

export default WecomRecipientPicker
