import { useEffect, useState, useCallback, useRef } from 'react'
import { Table, Tag, Input, Button, Space, message, Upload, Row, Col, Modal, Form, DatePicker } from 'antd'
import { SearchOutlined, ReloadOutlined, UploadOutlined, PlusOutlined, EditOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { productionApi } from '../../../services/api'
import { formatDate } from '../../../utils'

interface FrontRow {
  id: number
  customer_code: string | null
  sale_order_no: string | null
  order_date: string | null
  model_code: string | null
  color_spec: string | null
  qty: number | null
  delivery_date: string | null
  by_style: number | null
  shell_status: string | null
  frame_status: string | null
  handle_status: string | null
  bracket_status: string | null
  product_name: string | null
  remark: string | null
  status: string
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  completed: { label: '已完成', color: 'success' },
  pending: { label: '进行中', color: 'processing' },
  overdue: { label: '逾期', color: 'error' },
  abnormal: { label: '异常', color: 'warning' },
}

export default function FrontProcess() {
  const [data, setData] = useState<FrontRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filters, setFilters] = useState({ keyword: '', status: '' })
  const [editModal, setEditModal] = useState(false)
  const [editRecord, setEditRecord] = useState<FrontRow | null>(null)
  const [form] = Form.useForm()
  const uploadRef = useRef<any>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await productionApi.listFrontProcess({
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
      const res: any = await productionApi.importFrontProcess(file)
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
        customer_code: values.customer_code,
        sale_order_no: values.sale_order_no,
        model_code: values.model_code,
        color_spec: values.color_spec,
        qty: values.qty,
        delivery_date: values.delivery_date ? dayjs(values.delivery_date).format('YYYY-MM-DD') : null,
        shell_status: values.shell_status,
        frame_status: values.frame_status,
        handle_status: values.handle_status,
        bracket_status: values.bracket_status,
        product_name: values.product_name,
        remark: values.remark,
      }
      await productionApi.updateFrontProcess(editRecord.id, payload)
      message.success('保存成功')
      setEditModal(false)
      load()
    } catch (e: any) {
      message.error(e.message)
    }
  }

  const columns = [
    { title: '客户代码', dataIndex: 'customer_code', width: 110, ellipsis: true },
    { title: '销售订单号', dataIndex: 'sale_order_no', width: 150, ellipsis: true },
    { title: '下单日期', dataIndex: 'order_date', width: 90,
      render: (v: string) => formatDate(v),
    },
    { title: '型号', dataIndex: 'model_code', width: 180, ellipsis: true },
    { title: '颜色', dataIndex: 'color_spec', width: 120, ellipsis: true },
    { title: '数量', dataIndex: 'qty', width: 70, sorter: (a: FrontRow, b: FrontRow) => (a.qty || 0) - (b.qty || 0) },
    { title: '交期', dataIndex: 'delivery_date', width: 90,
      render: (v: string) => formatDate(v),
    },
    { title: '按款', dataIndex: 'by_style', width: 60 },
    { title: '壳体', dataIndex: 'shell_status', width: 80, ellipsis: true },
    { title: '框', dataIndex: 'frame_status', width: 80, ellipsis: true },
    { title: '手杆', dataIndex: 'handle_status', width: 80, ellipsis: true },
    { title: '支架圆盘', dataIndex: 'bracket_status', width: 90, ellipsis: true },
    { title: '产品名称', dataIndex: 'product_name', width: 200, ellipsis: true },
    { title: '备注', dataIndex: 'remark', width: 120, ellipsis: true },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: (v: string) => { const s = STATUS_MAP[v] || { label: v, color: 'default' }; return <Tag color={s.color}>{s.label}</Tag> },
    },
    {
      title: '操作', width: 60, fixed: 'right' as const,
      render: (_: any, row: FrontRow) => (
        <Button size="small" icon={<EditOutlined />} onClick={() => {
          setEditRecord(row)
          form.setFieldsValue({
            customer_code: row.customer_code,
            sale_order_no: row.sale_order_no,
            model_code: row.model_code,
            color_spec: row.color_spec,
            qty: row.qty,
            delivery_date: row.delivery_date ? dayjs(row.delivery_date) : null,
            shell_status: row.shell_status,
            frame_status: row.frame_status,
            handle_status: row.handle_status,
            bracket_status: row.bracket_status,
            product_name: row.product_name,
            remark: row.remark,
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
            <Input prefix={<SearchOutlined />} placeholder="搜索型号/订单号/产品" value={filters.keyword}
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
          scroll={{ x: 1800 }} size="small"
          pagination={{ total, current: page, pageSize, onChange: (p, ps) => { setPage(p); setPageSize(ps) }, showSizeChanger: true, showTotal: t => `共 ${t} 条` }}
          rowClassName={(row) => row.status === 'overdue' ? 'ant-table-row-danger' : row.status === 'abnormal' ? 'ant-table-row-warning' : ''}
        />
      </div>

      <Modal title="编辑前道记录" open={editModal} onCancel={() => { setEditModal(false); form.resetFields() }}
        onOk={() => form.submit()} width={700}>
        <Form form={form} layout="vertical" onFinish={handleEdit}>
          <Row gutter={16}>
            <Col span={8}><Form.Item name="customer_code" label="客户代码"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="sale_order_no" label="销售订单号"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="model_code" label="型号"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="color_spec" label="颜色"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="qty" label="数量"><Input type="number" /></Form.Item></Col>
            <Col span={8}><Form.Item name="delivery_date" label="交期"><DatePicker style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={6}><Form.Item name="shell_status" label="壳体"><Input /></Form.Item></Col>
            <Col span={6}><Form.Item name="frame_status" label="框"><Input /></Form.Item></Col>
            <Col span={6}><Form.Item name="handle_status" label="手杆"><Input /></Form.Item></Col>
            <Col span={6}><Form.Item name="bracket_status" label="支架圆盘"><Input /></Form.Item></Col>
            <Col span={16}><Form.Item name="product_name" label="产品名称"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="remark" label="备注"><Input /></Form.Item></Col>
          </Row>
        </Form>
      </Modal>
    </div>
  )
}
