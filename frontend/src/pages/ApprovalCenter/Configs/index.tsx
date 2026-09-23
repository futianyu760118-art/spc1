import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Drawer, Modal, Space, Switch, Table, Tabs, Tag, message } from 'antd'
import dayjs from 'dayjs'
import { approvalApi, type ApprovalConfigItem, type ApprovalNodeConfig, type ApprovalUserOption } from '../../../services/approval'
import ApprovalChainEditor from '../../../components/ApprovalChainEditor'
import { useAuthStore } from '../../../store/auth'
import BusinessTab from './BusinessTab'

type RoleItem = { role_code: string; role_name: string }

export default function ApprovalConfigs() {
  const [roles, setRoles] = useState<RoleItem[]>([])
  const [users, setUsers] = useState<ApprovalUserOption[]>([])
  const [activeTab, setActiveTab] = useState('chains')
  const [chainFocus, setChainFocus] = useState<string | null>(null)
  const hasPermission = useAuthStore(s => s.hasPermission)

  const loadOptions = useCallback(async () => {
    try {
      const [roleRes, userRes]: any[] = await Promise.all([approvalApi.roles(), approvalApi.users()])
      setRoles(roleRes.data?.items || [])
      setUsers(userRes.data?.items || [])
    } catch { /* 全局拦截器已提示 */ }
  }, [])

  useEffect(() => { loadOptions() }, [loadOptions])

  const roleOptions = useMemo(
    () => roles.map(r => ({ value: r.role_code, label: `${r.role_name}（${r.role_code}）` })),
    [roles],
  )

  const tabs = [
    {
      key: 'chains',
      label: '审批链',
      children: (
        <ChainTab roleOptions={roleOptions} users={users} focusBizType={chainFocus}
          onFocusHandled={() => setChainFocus(null)} />
      ),
    },
  ]
  if (hasPermission('approval.business', 'read')) {
    tabs.push({
      key: 'business',
      label: '业务接入',
      children: (
        <BusinessTab roleOptions={roleOptions} userOptions={users}
          onConfigureChain={bizType => { setChainFocus(bizType); setActiveTab('chains') }} />
      ),
    })
  }

  return (
    <Card title="审批配置">
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabs} />
    </Card>
  )
}

function ChainTab({ roleOptions, users, focusBizType, onFocusHandled }: {
  roleOptions: { value: string; label: string }[]
  users: ApprovalUserOption[]
  focusBizType: string | null
  onFocusHandled: () => void
}) {
  const [configs, setConfigs] = useState<ApprovalConfigItem[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState<ApprovalConfigItem | null>(null)
  const [editNodes, setEditNodes] = useState<ApprovalNodeConfig[]>([])
  const [editActive, setEditActive] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await approvalApi.configs()
      setConfigs(res.data?.items || [])
    } catch { /* 全局拦截器已提示 */ } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const openEdit = useCallback((cfg: ApprovalConfigItem) => {
    setEditing(cfg)
    setEditNodes((cfg.nodes || []).map((n, i) => ({ ...n, seq: n.seq || i + 1 })))
    setEditActive(cfg.is_active !== false)
  }, [])

  // 业务接入 Tab 的「配置链」跳转：等列表加载完成后定位并打开对应抽屉
  useEffect(() => {
    if (!focusBizType || loading) return
    const hit = configs.find(c => c.biz_type === focusBizType)
    if (hit) openEdit(hit)
    else message.warning('未找到该业务的审批链配置')
    onFocusHandled()
  }, [focusBizType, loading, configs, openEdit, onFocusHandled])

  const save = async () => {
    if (!editing) return
    setSaving(true)
    try {
      await approvalApi.saveConfig(editing.biz_type, { nodes: editNodes, is_active: editActive })
      message.success('保存成功，重新提交的单据将按新审批链执行')
      setEditing(null)
      load()
    } catch { /* 全局拦截器已提示 */ } finally { setSaving(false) }
  }

  const toggleActive = async (cfg: ApprovalConfigItem, next: boolean) => {
    if (!cfg.nodes?.length) {
      message.warning('请先配置审批链节点，再启用该业务')
      return
    }
    const doToggle = async () => {
      try {
        await approvalApi.saveConfig(cfg.biz_type, { nodes: cfg.nodes || [], is_active: next })
        message.success(next ? '已启用' : '已停用')
        load()
      } catch { /* 全局拦截器已提示 */ }
    }
    if (next) { await doToggle(); return }
    Modal.confirm({
      title: `停用「${cfg.biz_name || cfg.biz_type}」审批链？`,
      content: '停用后该业务不再产生新待办、也不再推送超时提醒；已提交的在途单据仍按提交时冻结的快照继续审批。',
      okText: '确认停用', okButtonProps: { danger: true },
      onOk: doToggle,
    })
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <Button onClick={load}>刷新</Button>
      </div>
      <Table<ApprovalConfigItem> rowKey="biz_type" loading={loading} dataSource={configs} pagination={false}
        columns={[
          { title: '业务名称', dataIndex: 'biz_name', render: (v: string, r: ApprovalConfigItem) => v || r.biz_type },
          { title: '业务标识', dataIndex: 'biz_type', width: 160, render: (v: string) => <span style={{ fontFamily: 'monospace' }}>{v}</span> },
          { title: '节点数', width: 80, render: (_: any, r: ApprovalConfigItem) => r.nodes?.length || 0 },
          { title: '审批链预览', render: (_: any, r: ApprovalConfigItem) => (
            <Space size={4} wrap>
              {(r.nodes || []).map((n, i) => (
                <Tag key={i} color={n.approvers?.length ? 'purple' : 'blue'}>
                  {n.label}{n.timeout_hours ? ` · ${n.timeout_hours}h` : ''}
                </Tag>
              ))}
              {(r.nodes || []).length === 0 ? <Tag>未配置</Tag> : null}
            </Space>
          ) },
          { title: '在途单据', width: 100, render: (_: any, r: ApprovalConfigItem) =>
            r.pending_count == null ? '-' : `${r.pending_count} 单` },
          { title: '启用', width: 80, render: (_: any, r: ApprovalConfigItem) => (
            <Switch checked={r.is_active !== false} disabled={!r.nodes?.length}
              onChange={next => toggleActive(r, next)} />
          ) },
          { title: '最后更新', width: 160, render: (_: any, r: ApprovalConfigItem) =>
            r.updated_at ? `${dayjs(r.updated_at).format('YYYY-MM-DD HH:mm')}${r.updated_by ? ' · ' + r.updated_by : ''}` : '-' },
          { title: '操作', width: 90, render: (_: any, r: ApprovalConfigItem) => (
            <Button size="small" type="link" onClick={() => openEdit(r)}>编辑</Button>
          ) },
        ]} />
      <Drawer title={editing ? `编辑审批链 - ${editing.biz_name || editing.biz_type}` : '编辑审批链'} width={880}
        open={!!editing} onClose={() => setEditing(null)}
        footer={
          <Space style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button onClick={() => setEditing(null)}>取消</Button>
            <Button type="primary" loading={saving} onClick={save}>保存</Button>
          </Space>
        }>
        {editing ? (
          <>
            <Alert type="warning" showIcon style={{ marginBottom: 12 }}
              message={`审批链变更只对之后重新提交的单据生效；当前在途 ${editing.pending_count ?? 0} 单沿用提交时冻结的快照。`} />
            <Space style={{ marginBottom: 12 }}>
              <span>启用状态</span>
              <Switch checked={editActive} onChange={setEditActive} />
              {!editActive ? <span style={{ color: '#dc2626', fontSize: 12 }}>停用后该业务不再产生新待办</span> : null}
            </Space>
            <ApprovalChainEditor nodes={editNodes} onChange={setEditNodes} roleOptions={roleOptions}
              userOptions={users} fieldOptions={editing.condition_field_options || []} />
          </>
        ) : null}
      </Drawer>
    </div>
  )
}
