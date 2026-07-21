import { useEffect, useState, useCallback } from 'react'
import {
  Table, Tag, Input, Select, Button, Space, message, Modal, Form, DatePicker, InputNumber,
  Upload, Popconfirm, Tooltip, Card, Row, Col,
} from 'antd'
import {
  SearchOutlined, ReloadOutlined, PlusOutlined, EditOutlined, DeleteOutlined,
  UploadOutlined, DownloadOutlined, FileTextOutlined, CheckCircleOutlined,
  ClockCircleOutlined, StopOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { materialApi } from '../../../services/api'
import { formatDate } from '../../../utils'

interface DetailRow {
  id: number
  detail_id?: number
  line_no?: number
  material_id?: number
  qty?: number | null
  delivery_qty?: number | null
  received_qty?: number | null
  sale_order_no?: string | null
  data_source?: string | null
}

interface HeadRow {
  id: number
  bill_no: string
  bill_date?: string | null
  bill_type?: string | null
  supplier_id?: number | null
  status?: string | null
  remark?: string | null
  data_source?: string | null
  voided_flag?: number | null
  closed_flag?: number | null
  detail_count?: number
  total_qty?: number | null
}

interface Stats {
  total: number
  audited: number
  pending: number
  closed: number
  voided: number
}

const STATUS_COLOR: Record<string, string> = {
  '0': 'default',
  '1': 'success',
  '2': 'processing',
  '3': 'error',
}
const STATUS_LABEL: Record<string, string> = {
  '0': '未审核',
  '1': '已审核',
  '2': '审核中',
  '3': '已关闭',
}

const STAT_CARDS = [
  { key: 'total', title: '委外订单总数', icon: <FileTextOutlined />, color: '#6366f1' },
  { key: 'audited', title: '已审核', icon: <CheckCircleOutlined />, color: '#059669' },
  { key: 'pending', title: '待审核', icon: <ClockCircleOutlined />, color: '#d97706' },
  { key: 'voided', title: '已作废', icon: <StopOutlined />, color: '#e11d48' },
] as const

export default function SubcontractOrders() {
  const [data, setData] = useState<HeadRow[]>([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<Stats>({ total: 0, audited: 0, pending: 0, closed: 0, voided: 0 })
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [includeVoided, setIncludeVoided] = useState(false)
  const [sortBy, setSortBy] = useState('')
  const [sortOrder, setSortOrder] = useState('')
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [batchOpen, setBatchOpen] = useState(false)
  const [batchLoading, setBatchLoading] = useState(false)
  const [batchForm] = Form.useForm()
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<HeadRow | null>(null)
  const [headForm] = Form.useForm()

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await materialApi.listSubcontractOrders({
        page, page_size: pageSize,
        keyword: keyword || undefined,
        include_voided: includeVoided,
        sort_by: sortBy || undefined,
        sort_order: sortOrder || undefined,
      })
      const d = res?.data
      setData(d?.items || [])
      setTotal(d?.total || 0)
      if (d?.stats) setStats(d.stats)
    } catch (e: any) {
      message.error(e?.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, keyword, includeVoided, sortBy, sortOrder])

  useEffect(() => { fetchData() }, [fetchData])

  const openCreate = () => {
    setEditing(null)
    headForm.resetFields()
    setEditOpen(true)
  }
  const openEdit = (row: HeadRow) => {
    setEditing(row)
    headForm.setFieldsValue({
      bill_no: row.bill_no,
      bill_date: row.bill_date ? dayjs(row.bill_date) : undefined,
      bill_type: row.bill_type,
      supplier_id: row.supplier_id,
      status: row.status,
      remark: row.remark,
    })
    setEditOpen(true)
  }

  const submitHead = async (values: any) => {
    const payload: any = { ...values }
    if (payload.bill_date) payload.bill_date = dayjs(payload.bill_date).format('YYYY-MM-DD')
    try {
      if (editing) {
        await materialApi.updateSubcontractOrder(editing.id, payload)
        message.success('已更新')
      } else {
        await materialApi.createSubcontractOrder(payload)
        message.success('已创建')
      }
      setEditOpen(false)
      fetchData()
    } catch (e: any) {
      message.error(e?.message || '保存失败')
    }
  }

  const remove = async (id: number) => {
    try {
      await materialApi.deleteSubcontractOrder(id)
      message.success('已删除')
      fetchData()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '删除失败')
    }
  }

  const submitBatch = async () => {
    const v = await batchForm.validateFields()
    setBatchLoading(true)
    try {
      const res: any = await materialApi.batchUpdateSubcontractOrders({
        ids: selectedIds,
        status: v.status || undefined,
        remark: v.remark || undefined,
      })
      message.success(`已更新 ${res?.data?.updated ?? 0} 条`)
      setBatchOpen(false)
      batchForm.resetFields()
      setSelectedIds([])
      fetchData()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '批量更新失败')
    } finally {
      setBatchLoading(false)
    }
  }

  const onImport = async (file: File) => {
    try {
      const res: any = await materialApi.importSubcontractOrders(file)
      message.success(`导入完成: ${JSON.stringify(res?.data)}`)
      fetchData()
    } catch (e: any) {
      message.error(e?.message || '导入失败')
    }
    return false
  }

  const onExport = async () => {
    try {
      const res: any = await materialApi.exportSubcontractOrders({
        keyword: keyword || undefined,
        include_voided: includeVoided,
        format: 'xlsx',
      })
      const url = window.URL.createObjectURL(new Blob([res]))
      const a = document.createElement('a')
      a.href = url
      a.download = 'subcontract_orders.xlsx'
      a.click()
      window.URL.revokeObjectURL(url)
    } catch (e: any) {
      message.error(e?.message || '导出失败')
    }
  }

  const columns = [
    { title: '单据编号', dataIndex: 'bill_no', width: 180, fixed: 'left' as const },
    { title: '日期', dataIndex: 'bill_date', width: 110, sorter: true,
      render: (v: string) => formatDate(v) },
    { title: '类型', dataIndex: 'bill_type', width: 120 },
    { title: '供应商ID', dataIndex: 'supplier_id', width: 90 },
    {
      title: '状态', dataIndex: 'status', width: 100,
      render: (v: string) => v ? <Tag color={STATUS_COLOR[v] || 'default'}>{STATUS_LABEL[v] || v}</Tag> : null,
    },
    { title: '明细数', dataIndex: 'detail_count', width: 90, align: 'right' as const, sorter: true },
    { title: '总数量', dataIndex: 'total_qty', width: 110, align: 'right' as const, sorter: true,
      render: (v: any) => v != null ? Number(v).toFixed(2) : '-' },
    {
      title: '来源', dataIndex: 'data_source', width: 90,
      render: (v: string) => v === 'erp' ? <Tag color="blue">ERP</Tag> : (v ? <Tag>{v}</Tag> : null),
    },
    { title: '摘要', dataIndex: 'remark', ellipsis: true },
    {
      title: '操作', key: 'op', width: 140, fixed: 'right' as const,
      render: (_: any, r: HeadRow) => (
        <Space>
          <Tooltip title={r.data_source === 'erp' ? 'ERP 数据请在 ERP 系统修改' : '编辑'}>
            <Button size="small" icon={<EditOutlined />}
              disabled={r.data_source === 'erp'} onClick={() => openEdit(r)} />
          </Tooltip>
          <Tooltip title={r.data_source === 'erp' ? 'ERP 数据不可删除' : '删除'}>
            <Popconfirm title="确认删除？" onConfirm={() => remove(r.id)} disabled={r.data_source === 'erp'}>
              <Button size="small" danger icon={<DeleteOutlined />} disabled={r.data_source === 'erp'} />
            </Popconfirm>
          </Tooltip>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {STAT_CARDS.map((card, i) => {
          const value = (stats as any)[card.key] ?? 0
          return (
            <Col span={6} key={i}>
              <Card size="small" className="card-modern" style={{ padding: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{
                    width: 44, height: 44, borderRadius: 10,
                    background: `${card.color}15`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 'calc(1.25rem * var(--font-size-scale))', color: card.color,
                  }}>
                    {card.icon}
                  </div>
                  <div>
                    <div style={{ fontSize: 'calc(1.375rem * var(--font-size-scale))', fontWeight: 700, color: '#1e293b' }}>
                      {value}
                    </div>
                    <div style={{ fontSize: 'calc(0.75rem * var(--font-size-scale))', color: '#64748b' }}>
                      {card.title}
                    </div>
                  </div>
                </div>
              </Card>
            </Col>
          )
        })}
      </Row>

      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <Input
              prefix={<SearchOutlined />}
              placeholder="搜索单据编号"
              value={keyword}
              onChange={e => { setKeyword(e.target.value); setPage(1) }}
              style={{ width: 240 }}
              allowClear
            />
          </Col>
          <Col>
            <Select
              value={includeVoided ? 'yes' : 'no'}
              onChange={v => { setIncludeVoided(v === 'yes'); setPage(1) }}
              style={{ width: 130 }}
            >
              <Select.Option value="no">隐藏作废</Select.Option>
              <Select.Option value="yes">包含作废</Select.Option>
            </Select>
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
              <Button icon={<DownloadOutlined />} onClick={onExport}>导出</Button>
              <Upload beforeUpload={onImport} showUploadList={false} accept=".csv">
                <Button icon={<UploadOutlined />}>导入 CSV</Button>
              </Upload>
              <Button
                disabled={selectedIds.length === 0}
                onClick={() => setBatchOpen(true)}
              >
                批量更新 {selectedIds.length > 0 ? `(${selectedIds.length})` : ''}
              </Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table<HeadRow>
          rowKey="id"
          dataSource={data}
          columns={columns}
          loading={loading}
          scroll={{ x: 1400 }}
          size="small"
          rowSelection={{
            selectedRowKeys: selectedIds,
            onChange: keys => setSelectedIds(keys as number[]),
          }}
          pagination={{
            total, current: page, pageSize,
            showSizeChanger: true, showTotal: t => `共 ${t} 条`,
          }}
          onChange={(pagination, _filters, sorter: any) => {
            setPage(pagination.current || 1)
            setPageSize(pagination.pageSize || 20)
            const f = sorter.field as string | undefined
            setSortBy(f || '')
            setSortOrder(sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : '')
          }}
          expandable={{
            rowExpandable: r => (r.detail_count ?? 0) > 0,
            expandedRowRender: r => <SubcontractDetailInline head={r} onChanged={fetchData} />,
          }}
        />
      </div>

      <Modal
        title={`批量更新 ${selectedIds.length} 条`}
        open={batchOpen}
        onCancel={() => setBatchOpen(false)}
        onOk={submitBatch}
        confirmLoading={batchLoading}
        destroyOnClose
      >
        <Form form={batchForm} layout="vertical">
          <Form.Item name="status" label="状态">
            <Input placeholder="如 0/1/2/3（留空不改）" />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} placeholder="留空不改" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editing ? `编辑 ${editing.bill_no}` : '新建委外订单'}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={() => headForm.submit()}
        width={640}
        destroyOnClose
      >
        <Form form={headForm} layout="vertical" onFinish={submitHead}>
          <Form.Item name="bill_no" label="单据编号" rules={[{ required: true }]}>
            <Input disabled={!!editing} />
          </Form.Item>
          <Form.Item name="bill_date" label="日期"><DatePicker style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="bill_type" label="类型"><Input /></Form.Item>
          <Form.Item name="supplier_id" label="供应商ID"><InputNumber style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="status" label="状态">
            <Select allowClear placeholder="0=未审核 1=已审核 2=审核中 3=已关闭">
              <Select.Option value="0">未审核</Select.Option>
              <Select.Option value="1">已审核</Select.Option>
              <Select.Option value="2">审核中</Select.Option>
              <Select.Option value="3">已关闭</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="remark" label="摘要"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

function SubcontractDetailInline({ head, onChanged }: { head: HeadRow; onChanged: () => void }) {
  const [items, setItems] = useState<DetailRow[]>([])
  const [loading, setLoading] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [addForm] = Form.useForm()
  const isErp = head.data_source === 'erp'

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    materialApi.getSubcontractOrderDetails(head.id, { page: 1, page_size: 500 })
      .then((res: any) => { if (!cancelled) setItems(res?.data?.items || []) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [head.id])

  const reload = () => {
    setLoading(true)
    materialApi.getSubcontractOrderDetails(head.id, { page: 1, page_size: 500 })
      .then((res: any) => setItems(res?.data?.items || []))
      .finally(() => setLoading(false))
  }

  const handleAdd = async (values: any) => {
    try {
      await materialApi.addSubcontractOrderDetail(head.id, values)
      message.success('已添加明细')
      addForm.resetFields()
      setAddOpen(false)
      reload()
      onChanged()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '添加失败')
    }
  }

  const handleDelete = async (detailId: number) => {
    try {
      await materialApi.deleteSubcontractOrderDetail(head.id, detailId)
      message.success('已删除')
      reload()
      onChanged()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '删除失败')
    }
  }

  const columns = [
    { title: '行号', dataIndex: 'line_no', width: 60 },
    { title: '物料ID', dataIndex: 'material_id', width: 90 },
    { title: '数量', dataIndex: 'qty', width: 90, align: 'right' as const,
      render: (v: any) => v != null ? Number(v).toFixed(2) : '-' },
    { title: '交货数', dataIndex: 'delivery_qty', width: 90, align: 'right' as const,
      render: (v: any) => v != null ? Number(v).toFixed(2) : '-' },
    { title: '已收', dataIndex: 'received_qty', width: 90, align: 'right' as const,
      render: (v: any) => v != null ? Number(v).toFixed(2) : '-' },
    { title: '销售订单号', dataIndex: 'sale_order_no', width: 140 },
    {
      title: '操作', key: 'op', width: 80,
      render: (_: any, r: DetailRow) => (
        <Tooltip title={r.data_source === 'erp' ? 'ERP 同步明细不可删除' : '删除'}>
          <Popconfirm title="删除该明细？" onConfirm={() => handleDelete(r.id)} disabled={r.data_source === 'erp'}>
            <Button size="small" danger icon={<DeleteOutlined />} disabled={r.data_source === 'erp'} />
          </Popconfirm>
        </Tooltip>
      ),
    },
  ]

  return (
    <div style={{ padding: '8px 16px 12px', background: 'rgba(248,250,252,.6)' }}>
      {!isErp && (
        <div style={{ marginBottom: 8 }}>
          <Button size="small" type="dashed" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
            添加明细
          </Button>
        </div>
      )}
      <Table<DetailRow>
        rowKey="id"
        size="small"
        loading={loading}
        dataSource={items}
        columns={columns}
        pagination={false}
      />
      <Modal
        title={`为 ${head.bill_no} 添加明细`}
        open={addOpen}
        onCancel={() => setAddOpen(false)}
        onOk={() => addForm.submit()}
        destroyOnClose
      >
        <Form form={addForm} layout="vertical" onFinish={handleAdd}>
          <Form.Item name="material_id" label="物料ID"><InputNumber style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="qty" label="数量"><InputNumber style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="sale_order_no" label="销售订单号"><Input /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
