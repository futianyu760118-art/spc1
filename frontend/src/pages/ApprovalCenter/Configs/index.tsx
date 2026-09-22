import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Drawer, Space, Table, message } from 'antd'
import dayjs from 'dayjs'
import { approvalApi } from '../../../services/approval'
import ApprovalChainEditor, { type ApprovalNodeRow } from '../../../components/ApprovalChainEditor'

type ApprovalConfigItem = {
  biz_type: string
  biz_name: string
  nodes: ApprovalNodeRow[]
  updated_by?: string | null
  updated_at?: string | null
}

type RoleItem = { role_code: string; role_name: string }

export default function ApprovalConfigs() {
  const [configs, setConfigs] = useState<ApprovalConfigItem[]>([])
  const [roles, setRoles] = useState<RoleItem[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState<ApprovalConfigItem | null>(null)
  const [editNodes, setEditNodes] = useState<ApprovalNodeRow[]>([])

  const load = async () => {
    setLoading(true)
    try {
      const res: any = await approvalApi.configs()
      setConfigs(res.data?.items || [])
    } catch { /* 全局拦截器已提示 */ } finally { setLoading(false) }
  }

  const loadRoles = async () => {
    try {
      const res: any = await approvalApi.roles()
      setRoles(res.data?.items || [])
    } catch { /* 全局拦截器已提示 */ }
  }

  useEffect(() => { load(); loadRoles() }, [])

  const roleOptions = useMemo(
    () => roles.map(r => ({ value: r.role_code, label: `${r.role_name}（${r.role_code}）` })),
    [roles],
  )

  const openEdit = (cfg: ApprovalConfigItem) => {
    setEditing(cfg)
    setEditNodes((cfg.nodes || []).map((n, i) => ({ ...n, seq: n.seq || i + 1 })))
  }

  const save = async () => {
    if (!editing) return
    setSaving(true)
    try {
      await approvalApi.saveConfig(editing.biz_type, { nodes: editNodes })
      message.success('保存成功，重新提交的单据将按新审批链执行')
      setEditing(null)
      load()
    } catch { /* 全局拦截器已提示 */ } finally { setSaving(false) }
  }

  return (
    <Card title="审批配置">
      <Table<ApprovalConfigItem> rowKey="biz_type" loading={loading} dataSource={configs} pagination={false}
        columns={[
          { title: '业务名称', dataIndex: 'biz_name', render: (v: string, r: ApprovalConfigItem) => v || r.biz_type },
          { title: '业务标识', dataIndex: 'biz_type', width: 180, render: (v: string) => <span style={{ fontFamily: 'monospace' }}>{v}</span> },
          { title: '节点数', width: 90, render: (_: any, r: ApprovalConfigItem) => r.nodes?.length || 0 },
          { title: '最后更新', width: 180, render: (_: any, r: ApprovalConfigItem) => r.updated_at ? dayjs(r.updated_at).format('YYYY-MM-DD HH:mm') : '-' },
          { title: '操作', width: 100, render: (_: any, r: ApprovalConfigItem) => (
            <Button size="small" type="link" onClick={() => openEdit(r)}>编辑</Button>
          ) },
        ]} />
      <Drawer title={editing ? `编辑审批链 - ${editing.biz_name || editing.biz_type}` : '编辑审批链'} width={760}
        open={!!editing} onClose={() => setEditing(null)}
        footer={
          <div style={{ textAlign: 'right' }}>
            <Space>
              <Button onClick={() => setEditing(null)}>取消</Button>
              <Button type="primary" loading={saving} onClick={save}>保存</Button>
            </Space>
          </div>
        }>
        <div style={{ color: '#94a3b8', marginBottom: 12 }}>审批链变更只对之后重新提交的单据生效</div>
        <ApprovalChainEditor nodes={editNodes} onChange={setEditNodes} roleOptions={roleOptions} />
      </Drawer>
    </Card>
  )
}
