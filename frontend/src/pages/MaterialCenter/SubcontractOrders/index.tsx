import { useEffect, useState, useCallback } from 'react'
import {
  Table, Tag, Input, Button, Space, message, Modal, Form, DatePicker, InputNumber,
  Upload, Popconfirm, Card, Row, Col, Statistic,
} from 'antd'
import {
  SearchOutlined, ReloadOutlined, PlusOutlined, EditOutlined, DeleteOutlined,
  UploadOutlined, DownloadOutlined, ExpandOutlined,
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

const STATUS_COLOR: Record<string, string> = {
  open: 'processing',
  closed: 'default',
  voided: 'error',
  audited: 'success',
}

export default function SubcontractOrders() {
  const [data, setData] = useState<HeadRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [includeVoided, setIncludeVoided] = useState(false)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [batchOpen, setBatchOpen] = useState(false)
  const [batchLoading, setBatchLoading] = useState(false)
  const [batchForm] = Form.useForm()
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<HeadRow | null>(null)
  const [detailOpen, setDetailOpen] = useState<HeadRow | null>(null)
  const [details, setDetails] = useState<DetailRow[]>([])
  const [detailsLoading, setDetailsLoading] = useState(false)
  const [detailForm] = Form.useForm()
  const [headForm] = Form.useForm()

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await materialApi.listSubcontractOrders({
        page, page_size: pageSize,
        keyword: keyword || undefined,
        include_voided: includeVoided,
      })
      const d = res?.data
      setData(d?.items || [])
      setTotal(d?.total || 0)
    } catch (e: any) {
      message.error(e?.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, keyword, includeVoided])

  useEffect(() => { fetchData() }, [fetchData])

  const openDetails = async (row: HeadRow) => {
    setDetailOpen(row)
    setDetailsLoading(true)
    try {
      const res: any = await materialApi.getSubcontractOrderDetails(row.id, { page: 1, page_size: 500 })
      setDetails(res?.data?.items || [])
    } finally {
      setDetailsLoading(false)
    }
  }

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

  const submitHead = async () => {
    const v = await headForm.validateFields()
    const payload: any = { ...v }
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

  const addDetail = async () => {
    if (!detailOpen) return
    const v = await detailForm.validateFields()
    try {
      await materialApi.addSubcontractOrderDetail(detailOpen.id, v)
      message.success('已添加明细')
      detailForm.resetFields()
      openDetails(detailOpen)
    } catch (e: any) {
      message.error(e?.message || '添加失败')
    }
  }

  const removeDetail = async (detailId: number) => {
    if (!detailOpen) return
    try {
      await materialApi.deleteSubcontractOrderDetail(detailOpen.id, detailId)
      message.success('已删除')
      openDetails(detailOpen)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '删除失败')
    }
  }

  const columns = [
    { title: '单据编号', dataIndex: 'bill_no', width: 180, fixed: 'left' as const },
    { title: '日期', dataIndex: 'bill_date', width: 110, render: (v: string) => formatDate(v) },
    { title: '类型', dataIndex: 'bill_type', width: 120 },
    { title: '供应商ID', dataIndex: 'supplier_id', width: 90 },
    {
      title: '状态', dataIndex: 'status', width: 100,
      render: (v: string) => v ? <Tag color={STATUS_COLOR[v] || 'default'}>{v}</Tag> : null,
    },
    { title: '明细数', dataIndex: 'detail_count', width: 80, align: 'right' as const },
    { title: '总数量', dataIndex: 'total_qty', width: 100, align: 'right' as const,
      render: (v: any) => v != null ? Number(v).toFixed(2) : '-' },
    {
      title: '来源', dataIndex: 'data_source', width: 90,
      render: (v: string) => v === 'erp' ? <Tag color="blue">ERP</Tag> : (v ? <Tag>{v}</Tag> : null),
    },
    { title: '摘要', dataIndex: 'remark', ellipsis: true },
    {
      title: '操作', key: 'op', width: 200, fixed: 'right' as const,
      render: (_: any, r: HeadRow) => (
        <Space>
          <Button size="small" onClick={() => openDetails(r)}>明细</Button>
          <Button size="small" icon={<EditOutlined />} disabled={r.data_source === 'erp'}
            onClick={() => openEdit(r)} />
          <Popconfirm title="确认删除？" onConfirm={() => remove(r.id)}
            disabled={r.data_source === 'erp'}>
            <Button size="small" danger icon={<DeleteOutlined />} disabled={r.data_source === 'erp'} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const detailColumns = [
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
        <Popconfirm title="删除该明细？" onConfirm={() => removeDetail(r.id)}
          disabled={r.data_source === 'erp'}>
          <Button size="small" danger icon={<DeleteOutlined />} disabled={r.data_source === 'erp'} />
        </Popconfirm>
      ),
    },
  ]

  return (
    <div className="p-4">
      <Card size="small" className="mb-3">
        <Row gutter={16}>
          <Col span={6}><Statistic title="总数" value={total} /></Col>
          <Col span={6}><Statistic title="当前页" value={data.length} /></Col>
        </Row>
      </Card>

      <Space className="mb-3" wrap>
        <Input
          placeholder="搜索 bill_no"
          prefix={<SearchOutlined />}
          value={keyword}
          onChange={(e) => { setKeyword(e.target.value); setPage(1) }}
          style={{ width: 240 }}
          allowClear
        />
        <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增</Button>
        <Upload beforeUpload={onImport} showUploadList={false} accept=".csv">
          <Button icon={<UploadOutlined />}>导入 CSV</Button>
        </Upload>
        <Button icon={<DownloadOutlined />} onClick={onExport}>导出</Button>
        <Button
          disabled={selectedIds.length === 0}
          onClick={() => setBatchOpen(true)}
        >
          批量改状态/备注 {selectedIds.length > 0 ? `(${selectedIds.length})` : ''}
        </Button>
      </Space>

      <Table<HeadRow>
        rowKey="id"
        loading={loading}
        dataSource={data}
        columns={columns}
        scroll={{ x: 1400 }}
        rowSelection={{
          selectedRowKeys: selectedIds,
          onChange: (keys) => setSelectedIds(keys as number[]),
        }}
        pagination={{
          current: page, pageSize, total,
          showSizeChanger: true, showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => { setPage(p); setPageSize(ps) },
        }}
        expandable={{
          expandRowByClick: false,
          expandIcon: () => <ExpandOutlined />,
          rowExpandable: (r) => (r.detail_count ?? 0) > 0,
          expandedRowRender: (r) => <SubcontractDetailInline headId={r.id} />,
        }}
      />

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
            <Input placeholder="如 open / closed / voided（留空不改）" />
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
        onOk={submitHead}
        width={640}
        destroyOnClose
      >
        <Form form={headForm} layout="vertical">
          <Form.Item name="bill_no" label="单据编号" rules={[{ required: true }]}>
            <Input disabled={!!editing} />
          </Form.Item>
          <Form.Item name="bill_date" label="日期"><DatePicker style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="bill_type" label="类型"><Input /></Form.Item>
          <Form.Item name="supplier_id" label="供应商ID"><InputNumber style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="status" label="状态"><Input placeholder="open / closed / voided" /></Form.Item>
          <Form.Item name="remark" label="摘要"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      <Modal
        title={detailOpen ? `明细 - ${detailOpen.bill_no}` : ''}
        open={!!detailOpen}
        onCancel={() => setDetailOpen(null)}
        footer={null}
        width={900}
        destroyOnClose
      >
        <Space className="mb-2" wrap>
          <InputNumber placeholder="物料ID" onChange={(v) => detailForm.setFieldValue('material_id', v)} />
          <InputNumber placeholder="数量" onChange={(v) => detailForm.setFieldValue('qty', v)} />
          <Input placeholder="销售订单号" onChange={(e) => detailForm.setFieldValue('sale_order_no', e.target.value)} />
          <Button icon={<PlusOutlined />} onClick={addDetail}>加明细</Button>
        </Space>
        <Table<DetailRow>
          rowKey="id"
          size="small"
          loading={detailsLoading}
          dataSource={details}
          columns={detailColumns}
          pagination={false}
          scroll={{ y: 360 }}
        />
      </Modal>
    </div>
  )
}

function SubcontractDetailInline({ headId }: { headId: number }) {
  const [items, setItems] = useState<DetailRow[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    materialApi.getSubcontractOrderDetails(headId, { page: 1, page_size: 500 })
      .then((res: any) => { if (!cancelled) setItems(res?.data?.items || []) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [headId])

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
  ]

  return (
    <Table<DetailRow>
      rowKey="id"
      size="small"
      loading={loading}
      dataSource={items}
      columns={columns}
      pagination={false}
    />
  )
}
