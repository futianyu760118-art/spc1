import { useEffect, useState, useCallback, useRef } from 'react'
import { Table, Tag, Input, Button, Space, message, Upload, Row, Col, Modal, Form, DatePicker } from 'antd'
import { SearchOutlined, ReloadOutlined, UploadOutlined, EditOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { productionApi } from '../../../services/api'
import { formatDate } from '../../../utils'

interface AssemblyRow {
  id: number
  assembly_group: string | null
  seq_no: number | null
  plan_date: string | null
  order_no: string | null
  model_code: string | null
  color_spec: string | null
  qty: number | null
  planned_qty: number | null
  online_date: string | null
  daily_plan_qty: number | null
  daily_complete_qty: number | null
  completion_rate: string | null
  work_hours: number | null
  remark: string | null
  status: string
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  completed: { label: '已完成', color: 'success' },
  pending: { label: '进行中', color: 'processing' },
  overdue: { label: '逾期', color: 'error' },
  abnormal: { label: '异常', color: 'warning' },
}

export default function Assembly() {
  const [data, setData] = useState<AssemblyRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filters, setFilters] = useState({ keyword: '', status: '' })
  const [editModal, setEditModal] = useState(false)
  const [editRecord, setEditRecord] = useState<AssemblyRow | null>(null)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await productionApi.listAssembly({
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
      const res: any = await productionApi.importAssembly(file)
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
        model_code: values.model_code,
        color_spec: values.color_spec,
        qty: values.qty,
        planned_qty: values.planned_qty,
        online_date: values.online_date ? dayjs(values.online_date).format('YYYY-MM-DD') : null,
        daily_plan_qty: values.daily_plan_qty,
        daily_complete_qty: values.daily_complete_qty,
        completion_rate: values.completion_rate,
        work_hours: values.work_hours,
        remark: values.remark,
      }
      await productionApi.updateAssembly(editRecord.id, payload)
      message.success('保存成功')
      setEditModal(false)
      load()
    } catch (e: any) {
      message.error(e.message)
    }
  }

  const columns = [
    { title: '总装', dataIndex: 'assembly_group', width: 60 },
    { title: '序号', dataIndex: 'seq_no', width: 60 },
    { title: '时间', dataIndex: 'plan_date', width: 90,
      render: (v: string) => formatDate(v),
    },
    { title: '订单号', dataIndex: 'order_no', width: 80 },
    { title: '型号', dataIndex: 'model_code', width: 180, ellipsis: true },
    { title: '颜色', dataIndex: 'color_spec', width: 130, ellipsis: true },
    { title: '数量', dataIndex: 'qty', width: 70, sorter: (a: AssemblyRow, b: AssemblyRow) => (a.qty || 0) - (b.qty || 0) },
    { title: '计划数量', dataIndex: 'planned_qty', width: 80 },
    { title: '上线时间', dataIndex: 'online_date', width: 90,
      render: (v: string) => formatDate(v),
    },
    { title: '当日排单', dataIndex: 'daily_plan_qty', width: 80 },
    { title: '当日完成', dataIndex: 'daily_complete_qty', width: 80 },
    { title: '完成率', dataIndex: 'completion_rate', width: 70, render: (v: string | null) => {
      if (!v) return '-'
      const pct = parseFloat(v)
      if (isNaN(pct)) return v
      if (pct >= 100) return <span style={{ color: '#16a34a' }}>{v}</span>
      if (pct >= 80) return <span style={{ color: '#f59e0b' }}>{v}</span>
      return <span style={{ color: '#e11d48' }}>{v}</span>
    }},
    { title: '工时', dataIndex: 'work_hours', width: 60 },
    { title: '备注', dataIndex: 'remark', width: 120, ellipsis: true },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: (v: string) => { const s = STATUS_MAP[v] || { label: v, color: 'default' }; return <Tag color={s.color}>{s.label}</Tag> },
    },
    {
      title: '操作', width: 60, fixed: 'right' as const,
      render: (_: any, row: AssemblyRow) => (
        <Button size="small" icon={<EditOutlined />} onClick={() => {
          setEditRecord(row)
          form.setFieldsValue({
            model_code: row.model_code, color_spec: row.color_spec,
            qty: row.qty, planned_qty: row.planned_qty,
            online_date: row.online_date ? dayjs(row.online_date) : null,
            daily_plan_qty: row.daily_plan_qty, daily_complete_qty: row.daily_complete_qty,
            completion_rate: row.completion_rate, work_hours: row.work_hours, remark: row.remark,
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
            <Input prefix={<SearchOutlined />} placeholder="搜索型号/订单号" value={filters.keyword}
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
          scroll={{ x: 1600 }} size="small"
          pagination={{ total, current: page, pageSize, onChange: (p, ps) => { setPage(p); setPageSize(ps) }, showSizeChanger: true, showTotal: t => `共 ${t} 条` }}
          rowClassName={(row) => row.status === 'overdue' ? 'ant-table-row-danger' : row.status === 'abnormal' ? 'ant-table-row-warning' : ''}
        />
      </div>

      <Modal title="编辑组装记录" open={editModal} onCancel={() => { setEditModal(false); form.resetFields() }}
        onOk={() => form.submit()} width={600}>
        <Form form={form} layout="vertical" onFinish={handleEdit}>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="model_code" label="型号"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="color_spec" label="颜色"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="qty" label="数量"><Input type="number" /></Form.Item></Col>
            <Col span={8}><Form.Item name="planned_qty" label="计划数量"><Input type="number" /></Form.Item></Col>
            <Col span={8}><Form.Item name="online_date" label="上线时间"><DatePicker style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="daily_plan_qty" label="当日排单"><Input type="number" /></Form.Item></Col>
            <Col span={8}><Form.Item name="daily_complete_qty" label="当日完成"><Input type="number" /></Form.Item></Col>
            <Col span={8}><Form.Item name="completion_rate" label="完成率"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="work_hours" label="工时"><Input type="number" /></Form.Item></Col>
            <Col span={16}><Form.Item name="remark" label="备注"><Input /></Form.Item></Col>
          </Row>
        </Form>
      </Modal>
    </div>
  )
}
