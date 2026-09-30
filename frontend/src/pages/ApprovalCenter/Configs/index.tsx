import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Card, Drawer, Input, Modal, Space, Switch, Table, Tabs, message } from 'antd'
import { InfoCircleOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { approvalApi, type ApprovalCondition, type ApprovalConfigItem, type ApprovalNodeConfig, type ApprovalUserOption } from '../../../services/approval'
import ApprovalChainEditor from '../../../components/ApprovalChainEditor'
import { useAuthStore } from '../../../store/auth'
import BusinessTab, { BizCell } from './BusinessTab'

type RoleItem = { role_code: string; role_name: string }

const OP_SYMBOL: Record<ApprovalCondition['op'], string> = {
  '>=': '≥', '<=': '≤', '>': '>', '<': '<', '==': '=', '!=': '≠', 'in': 'in',
}

const condsOf = (node: ApprovalNodeConfig): ApprovalCondition[] =>
  node.conditions?.length ? node.conditions : (node.condition ? [node.condition] : [])

const condChipText = (c: ApprovalCondition) => {
  const raw = Array.isArray(c.value) ? c.value.join(',') : String(c.value ?? '')
  // 金额类字段带 ¥ 与千分位，与原型预览一致；其余字段原样展示
  const amount = /amount/i.test(c.field)
  const val = amount && raw.trim() !== '' && Number.isFinite(Number(raw)) ? Number(raw).toLocaleString() : raw
  return `${OP_SYMBOL[c.op] || c.op}${amount ? '¥' : ''}${val}`
}

export default function ApprovalConfigs() {
  const [roles, setRoles] = useState<RoleItem[]>([])
  const [users, setUsers] = useState<ApprovalUserOption[]>([])
  const [activeTab, setActiveTab] = useState('chains')
  const [chainFocus, setChainFocus] = useState<string | null>(null)
  const [counts, setCounts] = useState<Partial<Record<'chains' | 'business', number>>>({})
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

  const onCount = useCallback((key: 'chains' | 'business', n: number) => {
    setCounts(prev => (prev[key] === n ? prev : { ...prev, [key]: n }))
  }, [])

  // 两个 Tab 的计数进入页面即预取（AntD Tabs 懒挂载，未点击的 Tab 不会自行上报，徽标会缺失）
  const loadCounts = useCallback(async () => {
    try {
      const [chainRes, bizRes]: any[] = await Promise.all([
        approvalApi.configs(),
        hasPermission('approval.business', 'read') ? approvalApi.businesses() : Promise.resolve(null),
      ])
      setCounts(prev => ({
        ...prev,
        chains: chainRes.data?.items?.length ?? 0,
        ...(bizRes ? { business: bizRes.data?.items?.length ?? 0 } : {}),
      }))
    } catch { /* 全局拦截器已提示 */ }
  }, [hasPermission])
  useEffect(() => { loadCounts() }, [loadCounts])

  const tabLabel = (key: 'chains' | 'business', text: string) => {
    const n = counts[key]
    return n == null ? text : <span>{text}<span className="sc-tab-count">{n}</span></span>
  }

  const tabs = [
    {
      key: 'chains',
      label: tabLabel('chains', '审批链'),
      children: (
        <ChainTab roleOptions={roleOptions} users={users} focusBizType={chainFocus}
          onFocusHandled={() => setChainFocus(null)} onCount={n => onCount('chains', n)} />
      ),
    },
  ]
  if (hasPermission('approval.business', 'read')) {
    tabs.push({
      key: 'business',
      label: tabLabel('business', '业务接入'),
      children: (
        <BusinessTab roleOptions={roleOptions} userOptions={users} onCount={n => onCount('business', n)}
          onConfigureChain={bizType => { setChainFocus(bizType); setActiveTab('chains') }} />
      ),
    })
  }

  return (
    <div className="sc-page ac-page">
      <Card styles={{ body: { padding: '0 12px 12px' } }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabs}
          tabBarExtraContent={{
            right: <span className="ac-head-hint">权限域：审批链 approval.config · 业务接入 approval.business</span>,
          }} />
      </Card>
    </div>
  )
}

function ChainTab({ roleOptions, users, focusBizType, onFocusHandled, onCount }: {
  roleOptions: { value: string; label: string }[]
  users: ApprovalUserOption[]
  focusBizType: string | null
  onFocusHandled: () => void
  onCount: (n: number) => void
}) {
  const [configs, setConfigs] = useState<ApprovalConfigItem[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState<ApprovalConfigItem | null>(null)
  const [editNodes, setEditNodes] = useState<ApprovalNodeConfig[]>([])
  const [editActive, setEditActive] = useState(true)
  const [keyword, setKeyword] = useState('')
  const [statusChip, setStatusChip] = useState<'all' | 'on' | 'off'>('all')
  const hasPermission = useAuthStore(s => s.hasPermission)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await approvalApi.configs()
      setConfigs(res.data?.items || [])
    } catch { /* 全局拦截器已提示 */ } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => { onCount(configs.length) }, [configs, onCount])

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

  const counts = useMemo(() => ({
    all: configs.length,
    on: configs.filter(c => c.is_active !== false).length,
    off: configs.filter(c => c.is_active === false).length,
  }), [configs])

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    return configs.filter(c => {
      if (statusChip === 'on' && c.is_active === false) return false
      if (statusChip === 'off' && c.is_active !== false) return false
      if (!kw) return true
      return (c.biz_name || '').toLowerCase().includes(kw) || c.biz_type.toLowerCase().includes(kw)
    })
  }, [configs, keyword, statusChip])

  return (
    <div className="ac-pane">
      <div className="ac-rule-note">
        <InfoCircleOutlined />
        <div>
          <b>审批链变更只对之后重新提交的单据生效。</b>
          单据提交时会冻结当时的审批链快照，在途单据按冻结快照继续审批，不受配置变更影响；停用后该业务不再产生新待办。
        </div>
      </div>

      <div className="sc-toolbar">
        <Input.Search allowClear placeholder="业务名称 / 标识" className="sc-search" style={{ width: 240 }}
          value={keyword} onChange={e => setKeyword(e.target.value)} />
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <span className={`sc-chip${statusChip === 'all' ? ' on' : ''}`} onClick={() => setStatusChip('all')}>
            全部 <span className="n">{counts.all}</span>
          </span>
          <span className={`sc-chip${statusChip === 'on' ? ' on' : ''}`} onClick={() => setStatusChip('on')}>
            已启用 <span className="n">{counts.on}</span>
          </span>
          <span className={`sc-chip${statusChip === 'off' ? ' on' : ''}`} onClick={() => setStatusChip('off')}>
            已停用 <span className="n">{counts.off}</span>
          </span>
        </div>
        <Button style={{ marginLeft: 'auto' }} onClick={load}>刷新</Button>
      </div>

      <Table<ApprovalConfigItem> rowKey="biz_type" loading={loading} dataSource={filtered}
        pagination={{ pageSize: 10, showTotal: t => `共 ${t} 条`, hideOnSinglePage: false }}
        columns={[
          { title: '业务', width: 216, render: (_: any, r: ApprovalConfigItem) => {
            const head = r.mode === 'sql' ? 'SQL 接入' : r.mode === 'builtin' ? '内置 Provider' : ''
            const tail = r.is_active === false ? '已停用' : (r.pending_count == null ? '' : `在途 ${r.pending_count} 单`)
            return <BizCell mode={r.mode} name={r.biz_name || r.biz_type} disabled={r.is_active === false}
              sub={[head, tail].filter(Boolean).join(' · ')} />
          } },
          { title: '业务标识', dataIndex: 'biz_type', width: 160, render: (v: string) => <span className="sc-mono">{v}</span> },
          { title: '审批链预览', render: (_: any, r: ApprovalConfigItem) => (
            (r.nodes || []).length === 0 ? <span className="sc-tag sc-tag-wait">未配置</span> : (
              <div className="ac-chain">
                {(r.nodes || []).map((n, i) => (
                  <Fragment key={i}>
                    {i > 0 ? <span className="ac-chain-arrow">→</span> : null}
                    <span className={`ac-chain-node${r.is_active === false ? ' off' : ''}`}>
                      {n.label || '未命名节点'}
                      {condsOf(n).map((c, ci) => (
                        <span key={ci} className="cond">·{condChipText(c)}</span>
                      ))}
                      {n.timeout_hours ? <span className="to">·{n.timeout_hours}h</span> : null}
                    </span>
                  </Fragment>
                ))}
              </div>
            )
          ) },
          { title: '节点', width: 70, align: 'right', render: (_: any, r: ApprovalConfigItem) => r.nodes?.length || 0 },
          { title: '超时提醒', width: 112, render: (_: any, r: ApprovalConfigItem) => {
            const total = r.nodes?.length || 0
            const configured = (r.nodes || []).filter(n => (n.timeout_hours ?? 0) > 0).length
            return configured
              ? <span className="sc-tag sc-tag-kit">{configured} / {total} 已配</span>
              : <span className="sc-tag sc-tag-wait">未配置</span>
          } },
          { title: '启用', width: 84, render: (_: any, r: ApprovalConfigItem) => (
            <Switch checked={r.is_active !== false} disabled={!r.nodes?.length}
              onChange={next => toggleActive(r, next)} />
          ) },
          { title: '最后更新', width: 176, render: (_: any, r: ApprovalConfigItem) =>
            r.updated_at ? <span className="sc-mono">{dayjs(r.updated_at).format('YYYY-MM-DD HH:mm')}{r.updated_by ? ` · ${r.updated_by}` : ''}</span> : '-' },
          { title: '操作', width: 90, render: (_: any, r: ApprovalConfigItem) => (
            <span className="sc-row-act">
              <Button size="small" type="link" onClick={() => openEdit(r)}>编辑</Button>
            </span>
          ) },
        ]} />
      <Drawer title={editing ? `编辑审批链 - ${editing.biz_name || editing.biz_type}` : '编辑审批链'} width={880}
        open={!!editing} onClose={() => setEditing(null)}
        rootClassName="sc-page ac-page sc-drawer ac-drawer"
        footer={
          <Space style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button onClick={() => setEditing(null)}>取消</Button>
            <Button type="primary" loading={saving} onClick={save}>保存审批链</Button>
          </Space>
        }>
        {editing ? (
          <>
            <div className="f-warn" style={{ marginBottom: 12 }}>
              审批链变更只对之后重新提交的单据生效；当前在途 {editing.pending_count ?? 0} 单沿用提交时冻结的快照。
            </div>
            <Space style={{ marginBottom: 12 }}>
              <span>启用状态</span>
              <Switch checked={editActive} onChange={setEditActive} />
              {!editActive ? <span className="ac-inline-warn">停用后该业务不再产生新待办</span> : null}
            </Space>
            <ApprovalChainEditor nodes={editNodes} onChange={setEditNodes} roleOptions={roleOptions}
              userOptions={users} fieldOptions={editing.condition_field_options || []} />
          </>
        ) : null}
      </Drawer>
    </div>
  )
}
