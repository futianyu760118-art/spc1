import { useEffect, useState } from 'react'
import { Table, Button, Modal, Form, Input, InputNumber, Select, Space, Tag, message, Row, Col } from 'antd'
import { PlusOutlined, EditOutlined, ReloadOutlined } from '@ant-design/icons'
import { ruleApi } from '../../services/api'
import { formatDateTime } from '../../utils'

const ruleTypeOptions = [
  { value: 'delivery_delay', label: '交期延期' },
  { value: 'shortage', label: '欠料风险' },
  { value: 'eta_delay', label: 'ETA延期' },
  { value: 'process_lag', label: '工序滞后' },
  { value: 'quality', label: '品质异常' },
  { value: 'inspection_ng', label: '客检NG' },
  { value: 'holiday_risk', label: '假期风险' },
  { value: 'long_lead', label: '长周期物料' },
]
const riskLevelOptions = [
  { value: 'red', label: '红灯（高风险）' },
  { value: 'yellow', label: '黄灯（中风险）' },
  { value: 'blue', label: '蓝灯（低风险）' },
  { value: 'green', label: '绿灯（正常）' },
]
const ruleTypeLabel: Record<string, string> = {
  delivery_delay: '交期延期',
  shortage: '欠料风险',
  eta_delay: 'ETA延期',
  process_lag: '工序滞后',
  quality: '品质异常',
  inspection_ng: '客检NG',
  holiday_risk: '假期风险',
  long_lead: '长周期物料',
}
const ruleTypeCategory: Record<string, string> = {
  delivery_delay: '评分因子',
  shortage: '评分因子',
  eta_delay: '评分因子',
  process_lag: '评分因子',
  quality: '评分因子',
  inspection_ng: '评分因子',
  holiday_risk: '监控规则',
  long_lead: '监控规则',
}

const monthOptions = Array.from({ length: 12 }, (_, i) => ({ value: i + 1, label: `${i + 1} 月` }))

export default function RiskRules() {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingRule, setEditingRule] = useState<any>(null)
  const [form] = Form.useForm()

  const fetchData = async () => {
    setLoading(true)
    try {
      const res: any = await ruleApi.list()
      setData(res.data || [])
    } catch {
      // 错误已由全局拦截器提示
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  const openAdd = () => {
    setEditingRule(null)
    form.resetFields()
    form.setFieldsValue({ threshold_days: 3, risk_level: 'yellow', is_active: true })
    setModalOpen(true)
  }

  const openEdit = (record: any) => {
    setEditingRule(record)
    const cond = record.condition_json || {}
    form.setFieldsValue({
      rule_code: record.rule_code,
      rule_name: record.rule_name,
      rule_type: record.rule_type,
      risk_level: record.risk_level,
      is_active: record.is_active,
      threshold_days: cond.threshold_days,
      delay_days_gt: cond.delay_days_gt,
      delay_days_lte: cond.delay_days_lte,
      shortage_qty_gt: cond.shortage_qty_gt,
      shortage_qty_lte: cond.shortage_qty_lte,
      open_count_gt: cond.open_count_gt,
      holiday_months: cond.holiday_months,
    })
    setModalOpen(true)
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      const {
        threshold_days, holiday_months,
        delay_days_gt, delay_days_lte,
        shortage_qty_gt, shortage_qty_lte,
        open_count_gt,
        ...rest
      } = values
      const condition_json: Record<string, any> = {}
      const rt = rest.rule_type
      // Build condition_json based on rule_type
      if (rt === 'delivery_delay' || rt === 'eta_delay') {
        if (delay_days_gt !== undefined && delay_days_gt !== null) condition_json.delay_days_gt = delay_days_gt
        if (delay_days_lte !== undefined && delay_days_lte !== null) condition_json.delay_days_lte = delay_days_lte
      } else if (rt === 'shortage') {
        if (shortage_qty_gt !== undefined && shortage_qty_gt !== null) condition_json.shortage_qty_gt = shortage_qty_gt
        if (shortage_qty_lte !== undefined && shortage_qty_lte !== null) condition_json.shortage_qty_lte = shortage_qty_lte
      } else if (rt === 'process_lag' || rt === 'long_lead') {
        if (threshold_days !== undefined && threshold_days !== null) condition_json.threshold_days = threshold_days
      } else if (rt === 'quality') {
        if (open_count_gt !== undefined && open_count_gt !== null) condition_json.open_count_gt = open_count_gt
      } else if (rt === 'holiday_risk') {
        if (threshold_days !== undefined && threshold_days !== null) condition_json.threshold_days = threshold_days
        if (holiday_months?.length) condition_json.holiday_months = holiday_months
      }
      // inspection_ng: no condition fields
      const payload = { ...rest, condition_json: Object.keys(condition_json).length ? condition_json : null }
      if (editingRule) {
        await ruleApi.update(editingRule.id, payload)
        message.success('规则更新成功')
      } else {
        await ruleApi.create(payload)
        message.success('规则创建成功')
      }
      setModalOpen(false)
      fetchData()
    } catch {
      // 错误已由全局拦截器提示
    }
  }

  const columns = [
    {
      title: '规则类型', dataIndex: 'rule_type', key: 'rule_type', width: 120,
      render: (t: string) => {
        const cat = ruleTypeCategory[t]
        return <Tag color={cat === '评分因子' ? 'blue' : 'green'}>{ruleTypeLabel[t] || t}</Tag>
      },
    },
    {
      title: '风险等级', dataIndex: 'risk_level', key: 'risk_level', width: 100,
      render: (l: string) => {
        const map: Record<string, { color: string; label: string }> = {
          red: { color: 'red', label: '红灯' },
          yellow: { color: 'orange', label: '黄灯' },
          blue: { color: 'blue', label: '蓝灯' },
          green: { color: 'green', label: '绿灯' },
        }
        const { color, label } = map[l] || { color: 'default', label: l }
        return <Tag color={color}>{label}</Tag>
      },
    },
    { title: '规则名称', dataIndex: 'rule_name', key: 'rule_name', ellipsis: true },
    {
      title: '条件',
      key: 'condition',
      width: 200,
      render: (_: any, record: any) => {
        const c = record.condition_json || {}
        const rt = record.rule_type
        if (rt === 'delivery_delay' || rt === 'eta_delay') {
          return <>延期 &gt;{c.delay_days_gt ?? '—'}天{c.delay_days_lte ? ` ≤${c.delay_days_lte}天` : ''}</>
        } else if (rt === 'shortage') {
          return <>欠料 &gt;{c.shortage_qty_gt ?? '—'}{c.shortage_qty_lte ? ` ≤${c.shortage_qty_lte}` : ''}</>
        } else if (rt === 'process_lag' || rt === 'long_lead') {
          return <>阈值 {c.threshold_days ?? '—'}天</>
        } else if (rt === 'quality') {
          return <>未关闭 &gt;{c.open_count_gt ?? '—'}条</>
        } else if (rt === 'holiday_risk') {
          const months = c.holiday_months || []
          return <>{months.length ? months.map((m: number) => <Tag key={m} style={{ fontSize: 11 }}>{m}月</Tag>) : '—'}{c.threshold_days ? ` 影响>${c.threshold_days}天` : ''}</>
        } else if (rt === 'inspection_ng') {
          return '检测到即触发'
        }
        return '—'
      },
    },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80,
      render: (v: boolean) => v !== false ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>,
    },
    { title: '版本', dataIndex: 'version', key: 'version', width: 60 },
    { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 170,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: '操作', key: 'action', width: 100, fixed: 'right' as const,
      render: (_: any, record: any) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} />
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <Select
              placeholder="按类型筛选"
              allowClear
              style={{ width: 160 }}
              options={ruleTypeOptions}
              onChange={(v) => {}}
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>新建规则</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="id"
          loading={loading}
          size="small"
          scroll={{ x: 1000 }}
          pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条`, pageSizeOptions: ['20', '50', '100'] }}
        />
      </div>

      <Modal
        title={editingRule ? '编辑规则' : '新建规则'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        width={520}
      >
        <Form form={form} layout="vertical">
          {!editingRule && (
            <Form.Item name="rule_code" label="规则编码" rules={[{ required: true, message: '请输入规则编码（唯一标识）' }]}>
              <Input placeholder="如 LONG_LEAD_90" />
            </Form.Item>
          )}
          <Form.Item name="rule_name" label="规则名称" rules={[{ required: true, message: '请输入规则名称' }]}>
            <Input placeholder="如 长周期物料检测-90天" />
          </Form.Item>
          <Form.Item name="rule_type" label="规则类型" rules={[{ required: true, message: '请选择' }]}>
            <Select options={ruleTypeOptions} placeholder="选择类型" disabled={!!editingRule} />
          </Form.Item>
          <Form.Item name="risk_level" label="风险等级" rules={[{ required: true }]}>
            <Select options={riskLevelOptions} />
          </Form.Item>
          {/* Dynamic condition fields based on rule_type */}
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.rule_type !== cur.rule_type}>
            {({ getFieldValue }) => {
              const rt = getFieldValue('rule_type')
              if (rt === 'delivery_delay' || rt === 'eta_delay') {
                return (
                  <>
                    <Form.Item name="delay_days_gt" label="延期天数 >">
                      <InputNumber min={0} max={365} className="w-full" placeholder="如 7" />
                    </Form.Item>
                    <Form.Item name="delay_days_lte" label="延期天数 ≤">
                      <InputNumber min={0} max={365} className="w-full" placeholder="如 14（可选上限）" />
                    </Form.Item>
                  </>
                )
              } else if (rt === 'shortage') {
                return (
                  <>
                    <Form.Item name="shortage_qty_gt" label="欠料数量 >">
                      <InputNumber min={0} className="w-full" placeholder="如 50" />
                    </Form.Item>
                    <Form.Item name="shortage_qty_lte" label="欠料数量 ≤">
                      <InputNumber min={0} className="w-full" placeholder="如 100（可选上限）" />
                    </Form.Item>
                  </>
                )
              } else if (rt === 'process_lag' || rt === 'long_lead') {
                return (
                  <Form.Item name="threshold_days" label="阈值（天）">
                    <InputNumber min={0} max={365} className="w-full" placeholder="如工序滞后 3 天，长周期 90 天" />
                  </Form.Item>
                )
              } else if (rt === 'quality') {
                return (
                  <Form.Item name="open_count_gt" label="未关闭品质异常数 >">
                    <InputNumber min={0} className="w-full" placeholder="如 1" />
                  </Form.Item>
                )
              } else if (rt === 'holiday_risk') {
                return (
                  <>
                    <Form.Item name="holiday_months" label="假期月份">
                      <Select mode="multiple" placeholder="选择假期月份（可多选）" options={monthOptions} />
                    </Form.Item>
                    <Form.Item name="threshold_days" label="影响天数 >">
                      <InputNumber min={0} max={30} className="w-full" placeholder="如停产影响 7 天" />
                    </Form.Item>
                  </>
                )
              } else if (rt === 'inspection_ng') {
                return <div style={{ color: '#94a3b8', fontSize: 12, marginBottom: 16 }}>客检结果为NG时自动触发，无需额外条件</div>
              }
              return null
            }}
          </Form.Item>
          <Form.Item name="is_active" label="状态" initialValue={true}>
            <Select options={[{ value: true, label: '启用' }, { value: false, label: '停用' }]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
