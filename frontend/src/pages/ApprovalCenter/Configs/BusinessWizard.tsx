import { Fragment, useEffect, useState } from 'react'
import { Button, Form, Input, Modal, Spin, Tag, message } from 'antd'
import { ApiOutlined, CodeOutlined, InfoCircleOutlined } from '@ant-design/icons'
import {
  approvalApi, type ApprovalBusinessItem, type ApprovalBusinessPayload,
  type ApprovalNodeConfig, type ApprovalUserOption,
} from '../../../services/approval'
import ApprovalChainEditor from '../../../components/ApprovalChainEditor'
import BusinessSqlStep, { MAPPING_FIELDS, type MappingField, type SqlStepValue } from './BusinessSqlStep'

type BasicValue = { bizType: string; bizName: string; description: string }

type WritebackValue = { table: string; id_column: string; status_column: string; status_map: Record<string, string> }

const STEP_ITEMS = [
  { title: '① 基本信息', hint: '名称 / 标识 / 说明' },
  { title: '② 取数配置', hint: 'SQL · 字段映射 · 条件字段' },
  { title: '③ 审批链与保存', hint: '节点配置 · 影响确认' },
  { title: '④ 回写映射', hint: '可选 · 终态同步业务表' },
]

const STEP_HINTS = ['填写基本信息', '配置取数与字段映射', '确认审批链并保存', '配置审批完成后回写业务状态（可选）']

const emptySqlValue = (): SqlStepValue => ({ sqlText: '', mapping: {}, deepLink: '', conditionFields: [] })

const emptyBasic = (): BasicValue => ({ bizType: '', bizName: '', description: '' })

const emptyWriteback = (): WritebackValue => ({
  table: '', id_column: '', status_column: '',
  status_map: { pending: '', approved: '', rejected: '', recalled: '' },
})

export default function BusinessWizard({ mode, record, initialStep = 0, roleOptions, userOptions, onClose, onSaved }: {
  mode: 'create' | 'edit'
  record?: ApprovalBusinessItem | null
  initialStep?: number
  roleOptions: { value: string; label: string }[]
  userOptions: ApprovalUserOption[]
  onClose: () => void
  onSaved: () => void
}) {
  const isEdit = mode === 'edit'
  const [step, setStep] = useState(initialStep)
  const [basic, setBasic] = useState<BasicValue>(() => isEdit && record ? {
    bizType: record.biz_type, bizName: record.biz_name, description: record.description || '',
  } : emptyBasic())
  const [sqlValue, setSqlValue] = useState<SqlStepValue>(() => isEdit && record ? {
    sqlText: record.sql_text || '',
    mapping: { ...(record.field_mapping || {}) },
    deepLink: record.deep_link_template || '',
    conditionFields: (record.condition_fields || []).map(f => ({ ...f })),
  } : emptySqlValue())
  const [nodes, setNodes] = useState<ApprovalNodeConfig[]>([])
  const [chainActive, setChainActive] = useState(true)
  const [loadingChain, setLoadingChain] = useState(isEdit)
  const [saving, setSaving] = useState(false)
  const [mappingFields, setMappingFields] = useState<MappingField[]>(MAPPING_FIELDS)
  const [writeback, setWriteback] = useState<WritebackValue>(() => {
    const wb = isEdit ? record?.writeback : null
    if (!wb) return emptyWriteback()
    return {
      table: wb.table || '', id_column: wb.id_column || '', status_column: wb.status_column || '',
      status_map: { ...emptyWriteback().status_map, ...(wb.status_map || {}) },
    }
  })

  // 映射字段清单由接口下发（业务标识演进时前端无需发版），失败回退本地缺省
  useEffect(() => {
    let cancelled = false
    approvalApi.businesses()
      .then((res: any) => {
        if (cancelled) return
        setMappingFields(res.data?.mapping_fields?.length ? res.data.mapping_fields : MAPPING_FIELDS)
      })
      .catch(() => { /* 全局拦截器已提示 */ })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!isEdit || !record) return
    let cancelled = false
    approvalApi.getConfig(record.biz_type)
      .then((res: any) => {
        if (cancelled) return
        setNodes(res.data?.nodes || [])
        setChainActive(res.data?.is_active !== false)
      })
      .catch(() => { /* 全局拦截器已提示 */ })
      .finally(() => { if (!cancelled) setLoadingChain(false) })
    return () => { cancelled = true }
  }, [isEdit, record])

  const validateBasic = () => {
    if (!basic.bizName.trim()) { message.warning('请填写业务名称'); return false }
    if (!isEdit && !/^[a-z][a-z0-9_]{2,63}$/.test(basic.bizType.trim())) {
      message.warning('业务标识需为小写字母开头、仅含小写字母/数字/下划线的 3~64 位字符串')
      return false
    }
    return true
  }

  const validateSql = () => {
    if (!sqlValue.sqlText.trim()) { message.warning('请填写取数 SQL'); return false }
    const missing = mappingFields.filter(f => f.required && !(sqlValue.mapping[f.key] || '').trim())
    if (missing.length) {
      message.warning(`请先映射必需字段：${missing.map(f => f.label).join('、')}`)
      return false
    }
    return true
  }

  const goNext = () => {
    if (step === 0 && !validateBasic()) return
    if (step === 1 && !validateSql()) return
    setStep(s => s + 1)
  }

  const save = async () => {
    if (!validateBasic()) { setStep(0); return }
    if (!validateSql()) { setStep(1); return }
    if (!nodes.length) { message.warning('请至少配置 1 个审批链节点'); return }
    const target = basic.bizType.trim()
    const fieldMapping = Object.fromEntries(
      Object.entries(sqlValue.mapping).filter(([, v]) => !!v && !!v.trim()),
    ) as ApprovalBusinessPayload['field_mapping']
    setSaving(true)
    try {
      const payload: ApprovalBusinessPayload = {
        biz_name: basic.bizName.trim(),
        sql_text: sqlValue.sqlText.trim(),
        field_mapping: fieldMapping,
        condition_fields: sqlValue.conditionFields.filter(f => f.value.trim()),
        deep_link_template: sqlValue.deepLink.trim(),
        description: basic.description.trim(),
        writeback: writeback.table.trim() ? writeback : undefined,
      }
      if (isEdit) {
        await approvalApi.updateBusiness(target, { ...payload, is_active: record?.is_active !== false })
      } else {
        await approvalApi.createBusiness({ ...payload, biz_type: target })
      }
      await approvalApi.saveConfig(target, { nodes, is_active: chainActive })
      message.success('已接入，待办工作台将自动聚合该业务')
      onSaved()
    } catch { /* 全局拦截器已提示 */ } finally { setSaving(false) }
  }

  const fieldOptions = sqlValue.conditionFields
    .filter(f => f.value.trim())
    .map(f => ({ value: f.value.trim(), label: f.label.trim() || f.value.trim() }))

  return (
    <Modal open width={900} maskClosable={false} onCancel={onClose}
      rootClassName="sc-page ac-page"
      title={
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          <span>{isEdit ? `编辑业务接入 · ${record?.biz_name || basic.bizType}` : '新增业务接入'}</span>
          <Tag color="blue" style={{ fontWeight: 400 }}>
            {isEdit ? 'SQL 配置 · 修改后即时生效' : 'SQL 配置 · 即时生效'}
          </Tag>
        </span>
      }
      styles={{ body: { padding: 0, maxHeight: 'calc(100vh - 260px)', overflowY: 'auto' } }}
      footer={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="ac-head-hint" style={{ marginRight: 'auto' }}>
            第 {step + 1} / 4 步 · {STEP_HINTS[step]}
          </span>
          <Button onClick={onClose}>取消</Button>
          {step > 0 ? <Button onClick={() => setStep(s => s - 1)}>上一步</Button> : null}
          {step < 3
            ? <Button type="primary" onClick={goNext}>下一步</Button>
            : <Button type="primary" loading={saving} onClick={save}>保存并启用</Button>}
        </div>
      }>
      <div className="ac-steps">
        {STEP_ITEMS.map((s, i) => (
          <Fragment key={i}>
            {i > 0 ? <span className={`ac-step-line${i <= step ? ' done' : ''}`} /> : null}
            <div className={`ac-step${i === step ? ' cur' : i < step ? ' done' : ''}`} onClick={() => setStep(i)}>
              <span className="no">{i + 1}</span>
              <div>
                <div className="s-name">{s.title}</div>
                <div className="s-hint">{s.hint}</div>
              </div>
            </div>
          </Fragment>
        ))}
      </div>

      <div style={{ padding: '16px 20px' }}>
        <div style={{ display: step === 0 ? 'block' : 'none' }}>
          <BasicStep value={basic} isEdit={isEdit} onChange={patch => setBasic(prev => ({ ...prev, ...patch }))} />
        </div>
        <div style={{ display: step === 1 ? 'block' : 'none' }}>
          <BusinessSqlStep value={sqlValue} fields={mappingFields}
            onChange={patch => setSqlValue(prev => ({ ...prev, ...patch }))} />
        </div>
        <div style={{ display: step === 2 ? 'block' : 'none' }}>
          <ChainStep nodes={nodes} onChange={setNodes} roleOptions={roleOptions} userOptions={userOptions}
            fieldOptions={fieldOptions} loading={loadingChain} />
        </div>
        <div style={{ display: step === 3 ? 'block' : 'none' }}>
          <WritebackStep value={writeback} onChange={patch => setWriteback(prev => ({ ...prev, ...patch }))} />
        </div>
      </div>
    </Modal>
  )
}

function BasicStep({ value, isEdit, onChange }: {
  value: BasicValue
  isEdit: boolean
  onChange: (patch: Partial<BasicValue>) => void
}) {
  return (
    <Form layout="vertical">
      <div style={{ display: 'flex', gap: 16 }}>
        <Form.Item label="业务名称" required style={{ flex: 1 }}>
          <Input value={value.bizName} maxLength={64} placeholder="如：采购付款申请"
            onChange={e => onChange({ bizName: e.target.value })} />
        </Form.Item>
        <Form.Item label="业务标识" required={!isEdit} style={{ flex: 1 }}
          extra={isEdit ? '业务标识保存后不可修改' : '小写字母开头，仅含小写字母/数字/下划线'}>
          <Input value={value.bizType} maxLength={64} disabled={isEdit} placeholder="如：purchase_payment"
            className="sc-mono" onChange={e => onChange({ bizType: e.target.value })} />
        </Form.Item>
      </div>
      <Form.Item label="说明">
        <Input.TextArea rows={2} value={value.description} maxLength={128} placeholder="该业务在待办工作台中的说明（选填）"
          onChange={e => onChange({ description: e.target.value })} />
      </Form.Item>
      <Form.Item label="接入方式">
        <div style={{ display: 'flex', gap: 10 }}>
          <div className="ac-access-card on">
            <div className="t"><CodeOutlined /> SQL 配置接入</div>
            <div className="d">配置只读 SQL + 字段映射 + 可选回写，零开发即可获得完整审批能力（中心内审批/批量通过/审批记录）。</div>
          </div>
          <div className="ac-access-card" onClick={() => message.info('内置业务需开发接入')}>
            <div className="t"><ApiOutlined /> 内置 Adapter 接入</div>
            <div className="d">开发实现 3 个方法，支持复用业务侧详情组件。</div>
          </div>
        </div>
      </Form.Item>
      <div className="f-note">
        业务标识用于审批链、待办聚合与深链，全局唯一；同一业务不允许重复注册。
      </div>
    </Form>
  )
}

function ChainStep({ nodes, onChange, roleOptions, userOptions, fieldOptions, loading }: {
  nodes: ApprovalNodeConfig[]
  onChange: (nodes: ApprovalNodeConfig[]) => void
  roleOptions: { value: string; label: string }[]
  userOptions: ApprovalUserOption[]
  fieldOptions: { value: string; label: string }[]
  loading: boolean
}) {
  return (
    <>
      <div className="ac-rule-note">
        <InfoCircleOutlined />
        <div>
          审批链决定流转顺序与条件路由；节点在提交时冻结快照，配置变更只影响之后提交的单据。
        </div>
      </div>
      {loading ? <Spin style={{ display: 'block', margin: '40px auto' }} /> : (
        <ApprovalChainEditor nodes={nodes} onChange={onChange} roleOptions={roleOptions}
          userOptions={userOptions} fieldOptions={fieldOptions} />
      )}
    </>
  )
}

function WritebackStep({ value, onChange }: {
  value: WritebackValue
  onChange: (patch: Partial<WritebackValue>) => void
}) {
  const items: [keyof WritebackValue['status_map'], string][] = [
    ['pending', '审批中'], ['approved', '已通过'], ['rejected', '已驳回'], ['recalled', '已撤回'],
  ]
  return (
    <Form layout="vertical">
      <div className="ac-rule-note">
        <InfoCircleOutlined />
        <div>可选：审批流转时把状态回写到业务表（同事务，强一致）。全部留空则不同步业务表。</div>
      </div>
      <div style={{ display: 'flex', gap: 16 }}>
        <Form.Item label="业务表名" style={{ flex: 1 }}><Input className="sc-mono" value={value.table}
          placeholder="如 purchase_payment" onChange={e => onChange({ table: e.target.value })} /></Form.Item>
        <Form.Item label="主键列" style={{ flex: 1 }}><Input className="sc-mono" value={value.id_column}
          placeholder="如 id" onChange={e => onChange({ id_column: e.target.value })} /></Form.Item>
        <Form.Item label="状态列" style={{ flex: 1 }}><Input className="sc-mono" value={value.status_column}
          placeholder="如 status" onChange={e => onChange({ status_column: e.target.value })} /></Form.Item>
      </div>
      <div style={{ display: 'flex', gap: 16 }}>
        {items.map(([k, label]) => (
          <Form.Item key={k} label={`${label}（${k}）→`} style={{ flex: 1 }}>
            <Input value={value.status_map[k] || ''} placeholder="业务表状态值"
              onChange={e => onChange({ status_map: { ...value.status_map, [k]: e.target.value } })} />
          </Form.Item>
        ))}
      </div>
    </Form>
  )
}
