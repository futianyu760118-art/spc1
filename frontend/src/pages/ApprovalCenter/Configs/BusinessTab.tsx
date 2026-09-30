import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Input, Modal, Space, Switch, Table, Tooltip, message } from 'antd'
import { ApiOutlined, AuditOutlined, CodeOutlined, InfoCircleOutlined, PlusOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { approvalApi, type ApprovalBusinessItem, type ApprovalUserOption } from '../../../services/approval'
import { useAuthStore } from '../../../store/auth'
import BusinessWizard from './BusinessWizard'

type WizardState = { mode: 'create' | 'edit'; record?: ApprovalBusinessItem; step?: number }
type BizChip = 'all' | 'builtin' | 'sql' | 'off'

// 审批链 Tab 复用：业务组合列（图标块 + 名称 + 副行）
export function BizCell({ mode, name, sub, disabled }: {
  mode?: 'builtin' | 'sql'
  name: string
  sub?: string
  disabled?: boolean
}) {
  const iconCls = disabled ? 'off' : mode === 'sql' ? 'sql' : ''
  return (
    <div className="ac-biz-cell">
      <span className={`ac-biz-ico ${iconCls}`}>
        {mode === 'sql' ? <CodeOutlined /> : mode === 'builtin' ? <AuditOutlined /> : <ApiOutlined />}
      </span>
      <div style={{ minWidth: 0 }}>
        <div className={`ac-biz-name${disabled ? ' off' : ''}`}>{name}</div>
        {sub ? <div className="ac-biz-sub" title={sub}>{sub}</div> : null}
      </div>
    </div>
  )
}

export default function BusinessTab({ roleOptions, userOptions, onConfigureChain, onCount }: {
  roleOptions: { value: string; label: string }[]
  userOptions: ApprovalUserOption[]
  onConfigureChain: (bizType: string) => void
  onCount: (n: number) => void
}) {
  const [items, setItems] = useState<ApprovalBusinessItem[]>([])
  const [loading, setLoading] = useState(false)
  const [wizard, setWizard] = useState<WizardState | null>(null)
  const [keyword, setKeyword] = useState('')
  const [chip, setChip] = useState<BizChip>('all')
  const [page, setPage] = useState(1)
  const hasPermission = useAuthStore(s => s.hasPermission)
  const canManage = hasPermission('approval.business', 'update')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await approvalApi.businesses()
      setItems(res.data?.items || [])
    } catch { /* 全局拦截器已提示 */ } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => { onCount(items.length) }, [items, onCount])

  const counts = useMemo(() => ({
    all: items.length,
    builtin: items.filter(i => i.mode === 'builtin').length,
    sql: items.filter(i => i.mode === 'sql').length,
    off: items.filter(i => i.is_active === false).length,
  }), [items])

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    return items.filter(i => {
      if (chip === 'builtin' && i.mode !== 'builtin') return false
      if (chip === 'sql' && i.mode !== 'sql') return false
      if (chip === 'off' && i.is_active !== false) return false
      if (!kw) return true
      return (i.biz_name || '').toLowerCase().includes(kw) || i.biz_type.toLowerCase().includes(kw)
    })
  }, [items, keyword, chip])

  const pickChip = (next: BizChip) => { setChip(next); setPage(1) }

  const toggleActive = async (row: ApprovalBusinessItem, next: boolean) => {
    const doToggle = async () => {
      try {
        // 更新端点会全量校验配置，启停需回传既有 SQL / 映射 / 条件字段
        await approvalApi.updateBusiness(row.biz_type, {
          biz_name: row.biz_name,
          sql_text: row.sql_text || '',
          field_mapping: row.field_mapping || {},
          condition_fields: row.condition_fields || [],
          deep_link_template: row.deep_link_template || '',
          description: row.description || '',
          is_active: next,
        })
        message.success(next ? '已启用' : '已停用')
        load()
      } catch { /* 全局拦截器已提示 */ }
    }
    if (next) { await doToggle(); return }
    Modal.confirm({
      title: `停用「${row.biz_name || row.biz_type}」？`,
      content: '停用后该业务不再聚合到待办工作台，也不再推送超时提醒；重新启用后恢复。',
      okText: '确认停用', okButtonProps: { danger: true },
      onOk: doToggle,
    })
  }

  return (
    <div className="ac-pane">
      <div className="ac-rule-note">
        <InfoCircleOutlined />
        <div>
          <b>内置业务</b>（代码 Provider）支持在审批中心内直接审批、批量通过；
          <b>SQL 接入业务</b>由管理员配置取数 SQL 与字段映射，即时生效，但仅支持待办聚合与跳转，审批动作需在业务系统内完成。
        </div>
      </div>

      <div className="sc-toolbar">
        <Input.Search allowClear placeholder="业务名称 / 标识" className="sc-search" style={{ width: 240 }}
          value={keyword} onChange={e => { setKeyword(e.target.value); setPage(1) }} />
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <span className={`sc-chip${chip === 'all' ? ' on' : ''}`} onClick={() => pickChip('all')}>
            全部 <span className="n">{counts.all}</span>
          </span>
          <span className={`sc-chip${chip === 'builtin' ? ' on' : ''}`} onClick={() => pickChip('builtin')}>
            内置 Provider <span className="n">{counts.builtin}</span>
          </span>
          <span className={`sc-chip${chip === 'sql' ? ' on' : ''}`} onClick={() => pickChip('sql')}>
            SQL 配置 <span className="n">{counts.sql}</span>
          </span>
          <span className={`sc-chip${chip === 'off' ? ' on' : ''}`} onClick={() => pickChip('off')}>
            已停用 <span className="n">{counts.off}</span>
          </span>
        </div>
        <Space style={{ marginLeft: 'auto' }}>
          <Button onClick={load}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} disabled={!canManage} onClick={() => setWizard({ mode: 'create' })}>
            新增业务接入
          </Button>
        </Space>
      </div>

      <Table<ApprovalBusinessItem> rowKey="biz_type" loading={loading} dataSource={filtered}
        pagination={{ current: page, pageSize: 10, showTotal: t => `共 ${t} 条`, hideOnSinglePage: false, onChange: setPage }}
        columns={[
          { title: '业务', width: 216, render: (_: any, r: ApprovalBusinessItem) => (
            <BizCell mode={r.mode} name={r.biz_name || r.biz_type} disabled={r.is_active === false}
              sub={r.description || (r.mode === 'sql' ? 'SQL 接入 · 即时生效' : '内置 Provider · 由开发接入')} />
          ) },
          { title: '业务标识', dataIndex: 'biz_type', width: 170, render: (v: string) => <span className="sc-mono">{v}</span> },
          { title: '接入方式', width: 130, render: (_: any, r: ApprovalBusinessItem) => r.mode === 'sql'
            ? <span className="sc-tag sc-tag-purple">SQL 配置</span>
            : <span className="sc-tag sc-tag-prod">内置 Provider</span> },
          { title: '在途单据', width: 100, render: (_: any, r: ApprovalBusinessItem) =>
            r.pending_count == null ? '-' : `${r.pending_count} 单` },
          { title: '审批链', width: 110, render: (_: any, r: ApprovalBusinessItem) => r.chain_node_count
            ? <span className="sc-tag sc-tag-done">{r.chain_node_count} 节点 · 已配置</span>
            : <span className="sc-tag sc-tag-wait">未配置</span> },
          { title: '启用', width: 90, render: (_: any, r: ApprovalBusinessItem) => r.mode === 'builtin'
            ? <Tooltip title="内置业务由代码接入"><span><Switch checked disabled /></span></Tooltip>
            : <Switch checked={r.is_active} disabled={!canManage} onChange={next => toggleActive(r, next)} /> },
          { title: '最后更新', width: 170, render: (_: any, r: ApprovalBusinessItem) =>
            r.updated_at ? <span className="sc-mono">{dayjs(r.updated_at).format('YYYY-MM-DD HH:mm')}{r.updated_by ? ` · ${r.updated_by}` : ''}</span> : '-' },
          { title: '操作', width: 190, render: (_: any, r: ApprovalBusinessItem) => (
            <span className="sc-row-act">
              {r.mode === 'sql' ? (
                <Button size="small" type="link" disabled={!canManage}
                  onClick={() => setWizard({ mode: 'edit', record: r })}>编辑</Button>
              ) : null}
              <Button size="small" type="link" onClick={() => onConfigureChain(r.biz_type)}>配置链</Button>
              {r.mode === 'sql' ? (
                <Button size="small" type="link" disabled={!canManage}
                  onClick={() => setWizard({ mode: 'edit', record: r, step: 1 })}>取数</Button>
              ) : null}
            </span>
          ) },
        ]} />

      {wizard ? (
        <BusinessWizard mode={wizard.mode} record={wizard.record} initialStep={wizard.step || 0}
          roleOptions={roleOptions} userOptions={userOptions}
          onClose={() => setWizard(null)}
          onSaved={() => { setWizard(null); load() }} />
      ) : null}
    </div>
  )
}
