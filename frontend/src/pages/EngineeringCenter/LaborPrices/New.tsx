import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  AutoComplete,
  Button,
  Card,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Tag,
  message,
} from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { useNavigate } from 'react-router-dom'
import { engineeringApi } from '../../../services/engineering'

interface DetailFormValue {
  process_type?: string
  gx?: number
  price?: number
  remark?: string
}

interface BomOption {
  bom_code: string
  product_code?: string
  product_name?: string
  workshop_name?: string
}

interface CurrentPrice {
  process_type: string
  price: number
  workshop_id?: string
  workshop_name?: string
  oa_main_id?: string
}

const COMMON_PROCESS_TYPES = ['组装', '组装前加工', '包装', '包装前加工']

function normalizeProcess(value?: string) {
  return (value || '').trim().toLowerCase()
}

export default function LaborPriceNew() {
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState<'draft' | 'pending' | null>(null)
  const [bomOptions, setBomOptions] = useState<BomOption[]>([])
  const [bomLoading, setBomLoading] = useState(false)
  const [currentPrices, setCurrentPrices] = useState<Record<string, CurrentPrice>>({})
  const [currentLoading, setCurrentLoading] = useState(false)

  const watchedDetails = Form.useWatch('details', form) as DetailFormValue[] | undefined
  const watchedBom = Form.useWatch('bom_code', form) as string | undefined

  const loadBoms = useCallback(async (keyword?: string) => {
    setBomLoading(true)
    try {
      const res: any = await engineeringApi.listLaborPriceBoms({
        keyword: keyword?.trim() || undefined,
        limit: 50,
      })
      setBomOptions(res.data || [])
    } catch {
      setBomOptions([])
    } finally {
      setBomLoading(false)
    }
  }, [])

  useEffect(() => {
    loadBoms()
  }, [loadBoms])

  const loadCurrentPrices = useCallback(async (bomCode?: string) => {
    if (!bomCode) {
      setCurrentPrices({})
      return
    }
    setCurrentLoading(true)
    try {
      const res: any = await engineeringApi.listCurrentLaborPrices({ bom_code: bomCode })
      const map: Record<string, CurrentPrice> = {}
      for (const item of (res.data || []) as CurrentPrice[]) {
        map[item.process_type] = item
      }
      setCurrentPrices(map)
      const first = (res.data || [])[0] as CurrentPrice | undefined
      if (first) {
        form.setFieldsValue({
          workshop_id: first.workshop_id,
          workshop_name: first.workshop_name,
        })
      }
    } catch {
      setCurrentPrices({})
    } finally {
      setCurrentLoading(false)
    }
  }, [form])

  useEffect(() => {
    loadCurrentPrices(watchedBom)
  }, [watchedBom, loadCurrentPrices])

  const handleBomChange = (value: string) => {
    const option = bomOptions.find((item) => item.bom_code === value)
    form.setFieldsValue({
      bom_code: value,
      product_code: option?.product_code,
      product_name: option?.product_name,
      workshop_id: undefined,
      workshop_name: option?.workshop_name,
    })
  }

  const handleProcessChange = (index: number, value: string) => {
    const current = currentPrices[value]
    if (!current) return
    const details = (form.getFieldValue('details') || []) as DetailFormValue[]
    const row = details[index] || {}
    if (row.price === undefined || row.price === null) {
      form.setFieldValue(['details', index, 'price'], current.price)
    }
    if (!row.remark && current.oa_main_id) {
      form.setFieldValue(['details', index, 'remark'], `引用 OA 主表 ${current.oa_main_id}`)
    }
  }

  const submitPrice = async (status: 'draft' | 'pending') => {
    let values: any
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    const details = (values.details || []) as DetailFormValue[]
    const processNames = details
      .map((item) => normalizeProcess(item.process_type))
      .filter(Boolean)
    if (processNames.length !== new Set(processNames).size) {
      message.warning('同一张工价单内工序不能重复')
      return
    }

    setSubmitting(status)
    try {
      await engineeringApi.createLaborPriceChange({
        bom_code: values.bom_code,
        product_code: values.product_code,
        product_name: values.product_name,
        workshop_id: values.workshop_id,
        workshop_name: values.workshop_name,
        effective_date: values.effective_date
          ? values.effective_date.format('YYYY-MM-DD')
          : undefined,
        reason: values.reason,
        remark: values.remark,
        status,
        details: details.map((item) => ({
          process_type: item.process_type,
          gx: item.gx,
          price: item.price,
          remark: item.remark,
        })),
      })
      message.success(status === 'draft' ? '已保存草稿' : '已提交审批')
      navigate('/engineering/labor-price-changes', { replace: true })
    } catch {
      // 错误已由全局拦截器提示
    } finally {
      setSubmitting(null)
    }
  }

  const processOptions = Array.from(
    new Set([...Object.keys(currentPrices), ...COMMON_PROCESS_TYPES]),
  ).map((value) => ({ value }))

  return (
    <div style={{ padding: 16 }}>
      <Card
        title="新建工价"
        extra={
          <Space>
            <Button onClick={() => navigate('/engineering/labor-price-changes')}>返回列表</Button>
            <Button loading={submitting === 'draft'} onClick={() => submitPrice('draft')}>
              保存草稿
            </Button>
            <Button
              type="primary"
              loading={submitting === 'pending'}
              onClick={() => submitPrice('pending')}
            >
              提交审批
            </Button>
          </Space>
        }
      >
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="先选 BOM，再按工序填写新单价；右侧会显示当前工价用于对比。"
            description="提交后进入待审批，审批通过前不影响排产。不同工序是独立明细，新增不会让其他工序失效。"
          />
          <Form form={form} layout="vertical" initialValues={{ details: [{}] }}>
            <Space size={16} wrap>
              <Form.Item
                name="bom_code"
                label="BOM"
                rules={[{ required: true, message: '请选择 BOM' }]}
                style={{ width: 360 }}
              >
                <Select
                  showSearch
                  allowClear
                  placeholder="搜索并选择 BOM / 产品"
                  filterOption={false}
                  loading={bomLoading}
                  options={bomOptions.map((item) => ({
                    value: item.bom_code,
                    label: `${item.bom_code}${item.product_name ? ` · ${item.product_name}` : ''}`,
                  }))}
                  onSearch={loadBoms}
                  onChange={handleBomChange}
                  notFoundContent={bomLoading ? '搜索中…' : '没有匹配的 BOM'}
                />
              </Form.Item>
              <Form.Item name="product_code" label="产品编码" style={{ width: 240 }}>
                <Input readOnly placeholder="选择 BOM 后自动带出" />
              </Form.Item>
              <Form.Item name="product_name" label="产品名称" style={{ width: 320 }}>
                <Input readOnly placeholder="选择 BOM 后自动带出" />
              </Form.Item>
            </Space>
            <Space size={16} wrap>
              <Form.Item name="workshop_id" label="车间 ID" style={{ width: 160 }}>
                <Input readOnly placeholder="自动" />
              </Form.Item>
              <Form.Item name="workshop_name" label="车间名称" style={{ width: 200 }}>
                <Input readOnly placeholder="自动" />
              </Form.Item>
              <Form.Item name="effective_date" label="生效日期" style={{ width: 180 }}>
                <DatePicker
                  style={{ width: '100%' }}
                  disabledDate={(current) => current && current < dayjs().startOf('day')}
                />
              </Form.Item>
            </Space>
            <Form.Item name="reason" label="调价/新增原因" style={{ width: 720 }}>
              <Input.TextArea rows={2} placeholder="说明为什么新增或调整工价" />
            </Form.Item>
            <Form.Item name="remark" label="备注" style={{ width: 720 }}>
              <Input.TextArea rows={2} placeholder="其他需要说明的内容" />
            </Form.Item>

            <Form.List name="details">
              {(fields, { add, remove }) => (
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  {fields.map((field, index) => {
                    const row = watchedDetails?.[field.name]
                    const processName = (row?.process_type || '').trim()
                    const current = currentPrices[processName]
                    const newPrice = row?.price
                    const diff =
                      current && newPrice !== undefined && newPrice !== null
                        ? Number((Number(newPrice) - current.price).toFixed(4))
                        : null
                    return (
                      <Space key={field.key} align="start" wrap>
                        <Form.Item
                          name={[field.name, 'process_type']}
                          label={index === 0 ? '工序' : undefined}
                          rules={[{ required: true, message: '请选择或输入工序' }]}
                          style={{ width: 180, marginBottom: 8 }}
                        >
                          <AutoComplete
                            options={processOptions}
                            placeholder="选择或输入工序"
                            filterOption={(input, option) =>
                              String(option?.value || '')
                                .toLowerCase()
                                .includes(input.toLowerCase())
                            }
                            onChange={(value) => handleProcessChange(index, value)}
                          />
                        </Form.Item>
                        <div style={{ width: 190, paddingTop: index === 0 ? 30 : 0 }}>
                          {current ? (
                            <Space size={4} wrap>
                              <Tag color="blue">当前 {current.price}</Tag>
                              {diff !== null && diff !== 0 && (
                                <Tag color={diff > 0 ? 'red' : 'green'}>
                                  {diff > 0 ? '+' : ''}
                                  {diff}
                                </Tag>
                              )}
                            </Space>
                          ) : (
                            <Tag color={processName ? 'orange' : 'default'}>
                              {processName ? '新增工序' : '未选择工序'}
                            </Tag>
                          )}
                        </div>
                        <Form.Item
                          name={[field.name, 'gx']}
                          label={index === 0 ? 'OA 工序码' : undefined}
                          style={{ width: 110, marginBottom: 8 }}
                        >
                          <InputNumber style={{ width: '100%' }} placeholder="gx" />
                        </Form.Item>
                        <Form.Item
                          name={[field.name, 'price']}
                          label={index === 0 ? '新单价' : undefined}
                          rules={[{ required: true, message: '请输入单价' }]}
                          style={{ width: 140, marginBottom: 8 }}
                        >
                          <InputNumber min={0} precision={4} style={{ width: '100%' }} />
                        </Form.Item>
                        <Form.Item
                          name={[field.name, 'remark']}
                          label={index === 0 ? '明细备注' : undefined}
                          style={{ width: 220, marginBottom: 8 }}
                        >
                          <Input placeholder="明细备注" />
                        </Form.Item>
                        {fields.length > 1 && (
                          <Button
                            type="text"
                            danger
                            icon={<DeleteOutlined />}
                            onClick={() => remove(field.name)}
                            style={{ marginTop: index === 0 ? 30 : 0 }}
                          />
                        )}
                      </Space>
                    )
                  })}
                  <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({})}>
                    添加工序明细
                  </Button>
                  {currentLoading && <span style={{ color: '#8c8c8c' }}>正在加载当前工价…</span>}
                </Space>
              )}
            </Form.List>
          </Form>
        </Space>
      </Card>
    </div>
  )
}
