import { useEffect, useState, useCallback, useRef } from 'react'
import { Table, Tag, Input, Button, Space, message, Upload, Row, Col, Modal, Form, DatePicker } from 'antd'
import { SearchOutlined, ReloadOutlined, UploadOutlined, EditOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { productionApi } from '../../../services/api'
import { formatDate } from '../../../utils'

interface SMTRow {
  id: number
  material_long_code: string | null
  material_name: string | null
  order_no: string | null
  qty: number | null
  material_confirm: string | null
  plan_date: string | null
  daily_plan_qty: number | null
  daily_complete_qty: number | null
  unit_price: number | null
  daily_amount: number | null
  completion_rate: string | null
  work_hours: number | null
  remark: string | null
  complete_time: string | null
  hour_capacity: number | null
  demand_time: string | null
  total_plan_complete: number | null
  status: string
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  completed: { label: '已完成', color: 'success' },
  pending: { label: '进行中', color: 'processing' },
  overdue: { label: '逾期', color: 'error' },
  abnormal: { label: '异常', color: 'warning' },
}

export default function SMT() {
  const [data, setData] = useState<SMTRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filters, setFilters] = useState({ keyword: '', status: '' })
  const [editModal, setEditModal] = useState(false)
  const [editRecord, setEditRecord] = useState<SMTRow | null>(null)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await productionApi.listSMT({
        page, page_size: pageSize,
        ...(filters.keyword ? { keyword: filters.keyword } : {}),
        ...(filters.status ? { status: filters.status } : {}),
      })
      setData(res.data.items)
      setTotal(res.data.total)
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, filters])

  useEffect(() => { load() }, [load])

  const handleImport = async (file: File) => {
    try {
      const res: any = await productionApi.importSMT(file)
      message.success(`导入完成：新增 ${res.data.created}，更新 ${res.data.updated}，跳过 ${res.data.skipped}`)
      load()
    } catch (e: any) {
      message.error(`导入失败：${e.message}`)
    }
    return false
  }

  const handleEdit = async (values: any) => {
    if (!editRecord) return
    try {
      const payload: Record<string, any> = {
        material_name: values.material_name,
        qty: values.qty,
        material_confirm: values.material_confirm,
        plan_date: values.plan_date ? dayjs(values.plan_date).format('YYYY-MM-DD') : null,
        daily_plan_qty: values.daily_plan_qty,
        daily_complete_qty: values.daily_complete_qty,
        unit_price: values.unit_price,
        daily_amount: values.daily_amount,
        completion_rate: values.completion_rate,
        work_hours: values.work_hours,
        remark: values.remark,
        complete_time: values.complete_time,
        hour_capacity: values.hour_capacity,
        demand_time: values.demand_time,
        total_plan_complete: values.total_plan_complete,
      }
      await productionApi.updateSMT(editRecord.id, payload)
      message.success('保存成功')
      setEditModal(false)
      load()
    } catch (e: any) {
      message.error(e.message)
    }
  }

  const columns = [
    { title: '物料长代码', dataIndex: 'material_long_code', width: 180, ellipsis: true, render: (v: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span> },
    { title: '物料名称', dataIndex: 'material_name', width: 200, ellipsis: true },
    { title: '订单号', dataIndex: 'order_no', width: 100 },
    { title: '订单数量', dataIndex: 'qty', width: 80, sorter: (a: SMTRow, b: SMTRow) => (a.qty || 0) - (b.qty || 0) },
    { title: '物料确认', dataIndex: 'material_confirm', width: 80, render: (v: string | null) => v === 'OK' ? <Tag color="success">OK</Tag> : v || '-' },
    { title: '计划日期', dataIndex: 'plan_date', width: 90,
      render: (v: string) => formatDate(v),
    },
    { title: '当日排单', dataIndex: 'daily_plan_qty', width: 80 },
    { title: '当日完成', dataIndex: 'daily_complete_qty', width: 80 },
    { title: '单价', dataIndex: 'unit_price', width: 70 },
    { title: '当日金额', dataIndex: 'daily_amount', width: 90 },
    { title: '完成率', dataIndex: 'completion_rate', width: 70 },
    { title: '工时', dataIndex: 'work_hours', width: 60 },
    { title: '备注', dataIndex: 'remark', width: 120, ellipsis: true },
    { title: '完成时间', dataIndex: 'complete_time', width: 90 },
    { title: '小时产能', dataIndex: 'hour_capacity', width: 80 },
    { title: '需求时间', dataIndex: 'demand_time', width: 90 },
    { title: '总计划完成', dataIndex: 'total_plan_complete', width: 100 },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: (v: string) => { const s = STATUS_MAP[v] || { label: v, color: 'default' }; return <Tag color={s.color}>{s.label}</Tag> },
    },
    {
      title: '操作', width: 60, fixed: 'right' as const,
      render: (_: any, row: SMTRow) => (
        <Button size="small" icon={<EditOutlined />} onClick={() => {
          setEditRecord(row)
          form.setFieldsValue({
            material_name: row.material_name, qty: row.qty, material_confirm: row.material_confirm,
            plan_date: row.plan_date ? dayjs(row.plan_date) : null,
            daily_plan_qty: row.daily_plan_qty, daily_complete_qty: row.daily_complete_qty,
            unit_price: row.unit_price, daily_amount: row.daily_amount,
            completion_rate: row.completion_rate, work_hours: row.work_hours,
            remark: row.remark, complete_time: row.complete_time,
            hour_capacity: row.hour_capacity, demand_time: row.demand_time,
            total_plan_complete: row.total_plan_complete,
          })
          setEditModal(true)
        }} />
      ),
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <Input prefix={<SearchOutlined />} placeholder="搜索物料/订单号" value={filters.keyword}
              onChange={e => { setFilters(f => ({ ...f, keyword: e.target.value })); setPage(1) }}
              style={{ width: 220 }} allowClear />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
              <Upload beforeUpload={(f) => { handleImport(f); return false }} showUploadList={false} accept=".csv">
                <Button icon={<UploadOutlined />}>导入CSV</Button>
              </Upload>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table rowKey="id" dataSource={data} columns={columns} loading={loading}
          scroll={{ x: 2200 }} size="small"
          pagination={{ total, current: page, pageSize, onChange: (p, ps) => { setPage(p); setPageSize(ps) }, showSizeChanger: true, showTotal: t => `共 ${t} 条` }}
        />
      </div>

      <Modal title="编辑贴片记录" open={editModal} onCancel={() => { setEditModal(false); form.resetFields() }}
        onOk={() => form.submit()} width={700}>
        <Form form={form} layout="vertical" onFinish={handleEdit}>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="material_name" label="物料名称"><Input /></Form.Item></Col>
            <Col span={6}><Form.Item name="qty" label="订单数量"><Input type="number" /></Form.Item></Col>
            <Col span={6}><Form.Item name="material_confirm" label="物料确认"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="plan_date" label="计划日期"><DatePicker style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="daily_plan_qty" label="当日排单"><Input type="number" /></Form.Item></Col>
            <Col span={8}><Form.Item name="daily_complete_qty" label="当日完成"><Input type="number" /></Form.Item></Col>
            <Col span={6}><Form.Item name="unit_price" label="单价"><Input type="number" /></Form.Item></Col>
            <Col span={6}><Form.Item name="daily_amount" label="当日金额"><Input type="number" /></Form.Item></Col>
            <Col span={6}><Form.Item name="completion_rate" label="完成率"><Input /></Form.Item></Col>
            <Col span={6}><Form.Item name="work_hours" label="工时"><Input type="number" /></Form.Item></Col>
            <Col span={8}><Form.Item name="complete_time" label="完成时间"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="hour_capacity" label="小时产能"><Input type="number" /></Form.Item></Col>
            <Col span={8}><Form.Item name="demand_time" label="需求时间"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="total_plan_complete" label="总计划完成"><Input type="number" /></Form.Item></Col>
            <Col span={16}><Form.Item name="remark" label="备注"><Input /></Form.Item></Col>
          </Row>
        </Form>
      </Modal>
    </div>
  )
}
