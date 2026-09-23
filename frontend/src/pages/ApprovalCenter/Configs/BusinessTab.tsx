import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Modal, Space, Switch, Table, Tag, Tooltip, message } from 'antd'
import dayjs from 'dayjs'
import { approvalApi, type ApprovalBusinessItem, type ApprovalUserOption } from '../../../services/approval'
import { useAuthStore } from '../../../store/auth'
import BusinessWizard from './BusinessWizard'

type WizardState = { mode: 'create' | 'edit'; record?: ApprovalBusinessItem; step?: number }

export default function BusinessTab({ roleOptions, userOptions, onConfigureChain }: {
  roleOptions: { value: string; label: string }[]
  userOptions: ApprovalUserOption[]
  onConfigureChain: (bizType: string) => void
}) {
  const [items, setItems] = useState<ApprovalBusinessItem[]>([])
  const [loading, setLoading] = useState(false)
  const [wizard, setWizard] = useState<WizardState | null>(null)
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
    <div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 12, alignItems: 'flex-start' }}>
        <Alert type="info" showIcon style={{ flex: 1 }}
          message="SQL 配置 = 只读取数 SQL + 字段映射，保存后立即聚合到待办工作台；内置业务由代码接入，不可在此修改。" />
        <Space>
          <Button onClick={load}>刷新</Button>
          <Button type="primary" disabled={!canManage} onClick={() => setWizard({ mode: 'create' })}>
            新增业务接入
          </Button>
        </Space>
      </div>

      <Table<ApprovalBusinessItem> rowKey="biz_type" loading={loading} dataSource={items} pagination={false}
        columns={[
          { title: '业务名称', dataIndex: 'biz_name', render: (v: string, r: ApprovalBusinessItem) => v || r.biz_type },
          { title: '业务标识', dataIndex: 'biz_type', width: 170, render: (v: string) => <span style={{ fontFamily: 'monospace' }}>{v}</span> },
          { title: '接入方式', width: 130, render: (_: any, r: ApprovalBusinessItem) => r.mode === 'sql'
            ? <Tag color="blue">SQL 配置</Tag>
            : <Tag color="purple">内置 Provider</Tag> },
          { title: '在途单据', width: 100, render: (_: any, r: ApprovalBusinessItem) =>
            r.pending_count == null ? '-' : `${r.pending_count} 单` },
          { title: '审批链', width: 100, render: (_: any, r: ApprovalBusinessItem) => r.chain_node_count
            ? `${r.chain_node_count} 节点`
            : <Tag>未配置</Tag> },
          { title: '启用', width: 90, render: (_: any, r: ApprovalBusinessItem) => r.mode === 'builtin'
            ? <Tooltip title="内置业务由代码接入"><span><Switch checked disabled /></span></Tooltip>
            : <Switch checked={r.is_active} disabled={!canManage} onChange={next => toggleActive(r, next)} /> },
          { title: '最后更新', width: 170, render: (_: any, r: ApprovalBusinessItem) =>
            r.updated_at ? `${dayjs(r.updated_at).format('YYYY-MM-DD HH:mm')}${r.updated_by ? ' · ' + r.updated_by : ''}` : '-' },
          { title: '操作', width: 190, render: (_: any, r: ApprovalBusinessItem) => (
            <Space size={0}>
              {r.mode === 'sql' ? (
                <Button size="small" type="link" disabled={!canManage}
                  onClick={() => setWizard({ mode: 'edit', record: r })}>编辑</Button>
              ) : null}
              <Button size="small" type="link" onClick={() => onConfigureChain(r.biz_type)}>配置链</Button>
              {r.mode === 'sql' ? (
                <Button size="small" type="link" disabled={!canManage}
                  onClick={() => setWizard({ mode: 'edit', record: r, step: 1 })}>取数</Button>
              ) : null}
            </Space>
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
