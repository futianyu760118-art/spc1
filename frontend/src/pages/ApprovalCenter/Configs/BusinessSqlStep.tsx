import { useMemo, useState } from 'react'
import { Alert, Button, Input, Select, Table, message } from 'antd'
import { CheckOutlined, CloseOutlined, PlusOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { approvalApi, type ApprovalConditionField, type ApprovalFieldMapping, type ApprovalMappingField, type TestSqlResult } from '../../../services/approval'

export type SqlStepValue = {
  sqlText: string
  mapping: ApprovalFieldMapping
  deepLink: string
  conditionFields: ApprovalConditionField[]
}

export type MappingField = ApprovalMappingField & { key: keyof ApprovalFieldMapping; hint?: string }

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

export default function BusinessSqlStep({ value, onChange, fields = MAPPING_FIELDS }: {
  value: SqlStepValue
  onChange: (patch: Partial<SqlStepValue>) => void
  fields?: MappingField[]
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
      <div className="ac-field-title first">
        <span>取数 SQL</span>
        <span className="sc-note" style={{ fontWeight: 400 }}>单条只读 SELECT / WITH；最多返回 200 行，5 秒超时</span>
        <Button style={{ marginLeft: 'auto' }} icon={<PlayCircleOutlined />} loading={testing} onClick={testSql}>
          测试取数
        </Button>
      </div>
      <Input.TextArea rows={7} value={value.sqlText} className="ac-sql-editor"
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

      <div className="ac-field-title">
        字段映射
        <span className="sc-note" style={{ fontWeight: 400 }}>测试取数后可下拉选择返回列；带 * 为必填</span>
      </div>
      <MappingTable mapping={value.mapping} options={columnOptions} fields={fields}
        onChange={(key, column) => onChange({ mapping: { ...value.mapping, [key]: column } })} />

      <div className="ac-field-title">
        深链模板
        <span className="sc-note" style={{ fontWeight: 400 }}>
          占位符 {'{no}'} / {'{id}'} / {'{title}'} 用映射后的值替换，留空则不提供跳转
        </span>
      </div>
      <Input value={value.deepLink} maxLength={256} placeholder="/purchase/pay/{no}"
        onChange={e => onChange({ deepLink: e.target.value })} />

      <div className="ac-field-title">
        条件字段声明
        <span className="sc-note" style={{ fontWeight: 400 }}>声明后可在审批链节点条件中选择</span>
      </div>
      <ConditionFieldsEditor fields={value.conditionFields}
        onChange={fields => onChange({ conditionFields: fields })} />
    </div>
  )
}

function MappingTable({ mapping, options, fields, onChange }: {
  mapping: ApprovalFieldMapping
  options: { value: string; label: string }[]
  fields: MappingField[]
  onChange: (key: keyof ApprovalFieldMapping, column?: string) => void
}) {
  return (
    <div>
      <div className="ac-map-head">
        <span>内部字段（SPC）</span>
        <span>来源列（SQL）</span>
        <span>说明</span>
        <span />
      </div>
      {fields.map(f => (
        <div className="ac-map-row" key={f.key}>
          <span className="src">
            {f.key}{f.required ? <span style={{ color: '#dc2626', fontWeight: 600 }}> *</span> : null}
          </span>
          <Select allowClear showSearch optionFilterProp="label" style={{ width: '100%' }}
            size="small"
            placeholder={f.required ? '必填：选择来源列' : '选填'}
            value={mapping[f.key] || undefined}
            options={options}
            onChange={col => onChange(f.key, col)} />
          <span className="sc-note">{f.label}{f.hint ? ` · ${f.hint}` : ''}</span>
          <span />
        </div>
      ))}
    </div>
  )
}

function ConditionFieldsEditor({ fields, onChange }: {
  fields: ApprovalConditionField[]
  onChange: (fields: ApprovalConditionField[]) => void
}) {
  const [editing, setEditing] = useState<number | null>(null)

  const updateAt = (index: number, patch: Partial<ApprovalConditionField>) =>
    onChange(fields.map((f, i) => (i === index ? { ...f, ...patch } : f)))

  const removeAt = (index: number) => {
    onChange(fields.filter((_, i) => i !== index))
    setEditing(prev => prev === null ? null : prev === index ? null : prev > index ? prev - 1 : prev)
  }

  const addField = () => {
    onChange([...fields, { value: '', label: '' }])
    setEditing(fields.length)
  }

  return (
    <div>
      {!fields.length ? (
        <div className="sc-note" style={{ marginBottom: 8 }}>未声明条件字段：审批链节点将无法配置触发条件</div>
      ) : null}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
        {fields.map((f, i) => {
          // 空字段（新增或值被清空）保持内联输入态；已声明 chip 点击可回到编辑态
          if (editing === i || !f.value.trim()) {
            return (
              <span key={i} className="ac-chip-edit">
                <Input size="small" className="sc-mono" style={{ width: 150 }} placeholder="字段名（如 amount）"
                  value={f.value} onChange={e => updateAt(i, { value: e.target.value })} />
                <Input size="small" style={{ width: 130 }} placeholder="显示名称（如 金额）"
                  value={f.label} onChange={e => updateAt(i, { label: e.target.value })} />
                <Button type="text" size="small" title="完成" icon={<CheckOutlined />} onClick={() => setEditing(null)} />
              </span>
            )
          }
          return (
            <span key={i} className="ac-chip-sm" title="点击编辑" onClick={() => setEditing(i)}>
              <span className="sc-mono">{f.value}</span>
              {f.label ? <span>· {f.label}</span> : null}
              <CloseOutlined className="ac-ico-xs" style={{ cursor: 'pointer' }}
                onClick={e => { e.stopPropagation(); removeAt(i) }} />
            </span>
          )
        })}
        {editing === null ? (
          <span className="ac-chip-sm add" onClick={addField}><PlusOutlined className="ac-ico-xs" /> 添加条件字段</span>
        ) : null}
      </div>
    </div>
  )
}
