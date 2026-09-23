import { useMemo, useState } from 'react'
import { Alert, Button, Input, Select, Space, Table, message } from 'antd'
import { DeleteOutlined, PlusOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { approvalApi, type ApprovalConditionField, type ApprovalFieldMapping, type TestSqlResult } from '../../../services/approval'

export type SqlStepValue = {
  sqlText: string
  mapping: ApprovalFieldMapping
  deepLink: string
  conditionFields: ApprovalConditionField[]
}

type MappingField = { key: keyof ApprovalFieldMapping; label: string; required: boolean; hint?: string }

export const MAPPING_FIELDS: MappingField[] = [
  { key: 'id', label: '单据 ID', required: true, hint: '必须是数字主键' },
  { key: 'no', label: '单号', required: true, hint: '深链跳转与展示' },
  { key: 'title', label: '标题', required: true },
  { key: 'applicant', label: '申请人', required: true },
  { key: 'submitted_at', label: '提交时间', required: true, hint: '用于排序与等待时长' },
  { key: 'current_node', label: '当前节点', required: true, hint: '需与审批链节点名称一致' },
  { key: 'summary', label: '摘要', required: false },
  { key: 'amount', label: '金额', required: false },
]

const SQL_EDITOR_STYLE = {
  fontFamily: 'Consolas, Monaco, "Courier New", monospace',
  fontSize: 12.5,
  background: '#0f172a',
  color: '#cbd5e1',
  borderColor: '#334155',
  borderRadius: 10,
  padding: '12px 16px',
  lineHeight: 1.8,
} as const

export default function BusinessSqlStep({ value, onChange }: {
  value: SqlStepValue
  onChange: (patch: Partial<SqlStepValue>) => void
}) {
  const [testing, setTesting] = useState(false)
  const [preview, setPreview] = useState<TestSqlResult | null>(null)
  const [sourceColumns, setSourceColumns] = useState<string[]>([])

  // 来源列下拉：测试取数的返回列 ∪ 已映射列，编辑回填后无需重新测试也能保留原选择
  const columnOptions = useMemo(() => {
    const mapped = Object.values(value.mapping).filter((v): v is string => !!v)
    return Array.from(new Set([...sourceColumns, ...mapped])).map(c => ({ value: c, label: c }))
  }, [sourceColumns, value.mapping])

  const testSql = async () => {
    if (!value.sqlText.trim()) { message.warning('请先填写取数 SQL'); return }
    setTesting(true)
    try {
      const res: any = await approvalApi.testSql(value.sqlText)
        const result: TestSqlResult = {
        columns: res.data?.columns || [],
        rows: res.data?.rows || [],
        elapsed_ms: res.data?.elapsed_ms ?? 0,
      }
      setPreview(result)
      setSourceColumns(result.columns)
      message.success(`取数成功：${result.rows.length} 行 · ${result.elapsed_ms}ms`)
    } catch { /* 全局拦截器已提示 */ } finally { setTesting(false) }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontWeight: 600 }}>取数 SQL</span>
        <span style={{ fontSize: 12, color: '#94a3b8' }}>单条只读 SELECT / WITH；最多返回 200 行，5 秒超时</span>
        <Button style={{ marginLeft: 'auto' }} icon={<PlayCircleOutlined />} loading={testing} onClick={testSql}>
          测试取数
        </Button>
      </div>
      <Input.TextArea rows={7} value={value.sqlText} style={SQL_EDITOR_STYLE}
        onChange={e => onChange({ sqlText: e.target.value })}
        placeholder={"SELECT id, apply_no AS no, title, applicant, submit_time, current_node\nFROM your_business_table\nWHERE status = 'pending'"} />

      {preview ? (
        <div style={{ marginTop: 12 }}>
          <Alert type="success" showIcon style={{ marginBottom: 8 }}
            message={`取数成功：${preview.rows.length} 行 · ${preview.elapsed_ms}ms · 返回 ${preview.columns.length} 列`} />
          <Table size="small" pagination={false} rowKey={(_, i) => String(i)} scroll={{ x: 'max-content', y: 200 }}
            dataSource={preview.rows}
            columns={preview.columns.map(col => ({
              title: col, dataIndex: col, key: col, width: 160, ellipsis: true,
              render: (v: any) => v == null ? <span style={{ color: '#cbd5e1' }}>NULL</span> : String(v),
            }))} />
        </div>
      ) : null}

      <div style={{ fontWeight: 600, margin: '16px 0 8px' }}>
        字段映射
        <span style={{ fontSize: 12, fontWeight: 400, color: '#94a3b8', marginLeft: 8 }}>
          测试取数后可下拉选择返回列；带 * 为必填
        </span>
      </div>
      <MappingTable mapping={value.mapping} options={columnOptions}
        onChange={(key, column) => onChange({ mapping: { ...value.mapping, [key]: column } })} />

      <div style={{ fontWeight: 600, margin: '16px 0 8px' }}>
        深链模板
        <span style={{ fontSize: 12, fontWeight: 400, color: '#94a3b8', marginLeft: 8 }}>
          占位符 {'{no}'} / {'{id}'} / {'{title}'} 用映射后的值替换，留空则不提供跳转
        </span>
      </div>
      <Input value={value.deepLink} maxLength={256} placeholder="/purchase/pay/{no}"
        onChange={e => onChange({ deepLink: e.target.value })} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '16px 0 8px' }}>
        <span style={{ fontWeight: 600 }}>条件字段声明</span>
        <span style={{ fontSize: 12, color: '#94a3b8' }}>声明后可在审批链节点条件中选择</span>
        <Button size="small" type="link" icon={<PlusOutlined />} style={{ marginLeft: 'auto' }}
          onClick={() => onChange({ conditionFields: [...value.conditionFields, { value: '', label: '' }] })}>
          添加字段
        </Button>
      </div>
      <ConditionFieldsEditor fields={value.conditionFields}
        onChange={fields => onChange({ conditionFields: fields })} />
    </div>
  )
}

function MappingTable({ mapping, options, onChange }: {
  mapping: ApprovalFieldMapping
  options: { value: string; label: string }[]
  onChange: (key: keyof ApprovalFieldMapping, column?: string) => void
}) {
  return (
    <Table<MappingField> size="small" pagination={false} rowKey="key" dataSource={MAPPING_FIELDS}
      columns={[
        { title: '内部字段', width: 200, render: (_, f) => (
          <Space size={6}>
            <span style={{ fontFamily: 'monospace' }}>{f.key}</span>
            {f.required
              ? <span style={{ color: '#dc2626', fontWeight: 600 }}>*</span>
              : <span style={{ fontSize: 11, color: '#94a3b8' }}>可选</span>}
          </Space>
        ) },
        { title: '来源列', render: (_, f) => (
          <Select allowClear showSearch optionFilterProp="label" style={{ width: '100%' }}
            placeholder={f.required ? '必填：选择来源列' : '选填'}
            value={mapping[f.key] || undefined}
            options={options}
            onChange={col => onChange(f.key, col)} />
        ) },
        { title: '说明', width: 280, render: (_, f) => (
          <span style={{ fontSize: 12, color: '#64748b' }}>{f.label}{f.hint ? ` · ${f.hint}` : ''}</span>
        ) },
      ]} />
  )
}

function ConditionFieldsEditor({ fields, onChange }: {
  fields: ApprovalConditionField[]
  onChange: (fields: ApprovalConditionField[]) => void
}) {
  const updateAt = (index: number, patch: Partial<ApprovalConditionField>) =>
    onChange(fields.map((f, i) => (i === index ? { ...f, ...patch } : f)))

  if (!fields.length) {
    return <div style={{ fontSize: 12, color: '#94a3b8' }}>未声明条件字段：审批链节点将无法配置触发条件</div>
  }
  return (
    <div>
      {fields.map((f, i) => (
        <Space key={i} align="baseline" style={{ display: 'flex', marginBottom: 8 }} wrap>
          <Input size="small" style={{ width: 200, fontFamily: 'monospace' }} placeholder="字段名（如 amount）"
            value={f.value} onChange={e => updateAt(i, { value: e.target.value })} />
          <Input size="small" style={{ width: 200 }} placeholder="显示名称（如 金额）"
            value={f.label} onChange={e => updateAt(i, { label: e.target.value })} />
          <Button size="small" type="link" danger icon={<DeleteOutlined />}
            onClick={() => onChange(fields.filter((_, fi) => fi !== i))} />
        </Space>
      ))}
    </div>
  )
}
