import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Descriptions, Table, Tag, Spin, Button, message, Tabs, Card, Row, Col, Timeline } from 'antd'
import {
  ArrowLeftOutlined,
  ShoppingCartOutlined,
  WarningOutlined,
  ExperimentOutlined,
} from '@ant-design/icons'
import RiskBadge from '../../../components/RiskBadge'
import StatusTag from '../../../components/StatusTag'
import { orderApi, etaApi } from '../../../services/api'

interface OrderDetailData {
  id: number
  order_no: string
  line_no: string | null
  customer: string | null
  customer_code: string | null
  product_code: string | null
  product_name: string | null
  product_model: string | null
  order_qty: number | null
  promised_date: string | null
  planned_start_date: string | null
  batch_no: string | null
  department: string | null
  audit_date: string | null
  owner: string | null
  status: string
  risk_level: string | null
  data_source: string | null
  lines: any[]
  material_demands: any[]
  bindings: any[]
  shortage_count: number
  in_transit_count: number
  latest_eta: string | null
  issues: any[]
}

interface ProductMaterialItem {
  material_code: string
  material_name: string | null
  material_property: number | null
  material_property_label: string | null
  material_type: string | null
  spec_model: string | null
  unit: string | null
  req_qty: number | null
  req_date: string | null
  allocated_qty: number
  shortage_qty: number
  shortage_flag: boolean
  status: string
  status_label: string
  po_no: string | null
  supplier_name: string | null
  po_qty: number | null
  received_qty: number | null
  eta: string | null
  actual_arrival_date: string | null
  inspection_date: string | null
  po_count: number
  is_stagnant: boolean
  stagnant_qty: number | null
}

interface ProductMaterialGroup {
  line_no: string | null
  product_code: string | null
  product_name: string | null
  product_model: string | null
  order_qty: number | null
  promised_date: string | null
  total_materials: number
  not_ordered_count: number
  shortage_count: number
  overdue_count: number
  arrived_count: number
  kit_rate: number
  materials: ProductMaterialItem[]
}

const STATUS_COLOR: Record<string, string> = {
  not_ordered: 'default',
  self_made_unlinked: 'blue',
  pending: 'processing',
  overdue: 'error',
  partial_received: 'warning',
  fully_received: 'success',
}

export default function OrderDetail() {
  const { orderNo, lineNo } = useParams<{ orderNo: string; lineNo: string }>()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<OrderDetailData | null>(null)
  const [loading, setLoading] = useState(true)
  const [etaHistory, setEtaHistory] = useState<any[]>([])
  const [productMaterials, setProductMaterials] = useState<ProductMaterialGroup[]>([])
  const [productMaterialsLoading, setProductMaterialsLoading] = useState(false)

  const fetchDetail = async () => {
    if (!orderNo) return
    setLoading(true)
    try {
      const res: any = await orderApi.getDetail(orderNo, lineNo)
      setDetail(res.data)
      setProductMaterialsLoading(true)
      const materialRes: any = await orderApi.getProductMaterials(orderNo, lineNo ? { line_no: lineNo } : {})
      setProductMaterials(materialRes.data || [])
    } catch {
      message.error('获取订单详情失败')
    } finally {
      setLoading(false)
      setProductMaterialsLoading(false)
    }
  }

  useEffect(() => {
    fetchDetail()
  }, [orderNo, lineNo])

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>
  }

  if (!detail) {
    return <div style={{ textAlign: 'center', padding: 80, color: '#94a3b8' }}>订单不存在</div>
  }

  const materialColumns = [
    { title: '物料编码', dataIndex: 'material_code', key: 'material_code', width: 120 },
    { title: '物料名称', dataIndex: 'material_name', key: 'material_name', ellipsis: true },
    { title: '需求量', dataIndex: 'req_qty', key: 'req_qty', width: 90, render: (v: number) => v?.toLocaleString() },
    { title: '需求日期', dataIndex: 'req_date', key: 'req_date', width: 105 },
    { title: '已分配', dataIndex: 'allocated_qty', key: 'allocated_qty', width: 90, render: (v: number) => v?.toLocaleString() },
    {
      title: '欠料量', dataIndex: 'shortage_qty', key: 'shortage_qty', width: 90,
      render: (v: number) => v > 0 ? <span style={{ color: '#e11d48', fontWeight: 600 }}>{v?.toLocaleString()}</span> : <span style={{ color: '#10b981' }}>0</span>,
    },
    {
      title: '欠料', dataIndex: 'shortage_flag', key: 'shortage_flag', width: 70,
      render: (v: boolean) => v ? <Tag color="red">欠料</Tag> : <Tag color="green">齐套</Tag>,
    },
  ]

  const bindingColumns = [
    { title: '物料编码', dataIndex: 'material_code', key: 'material_code', width: 120 },
    { title: 'PO号', dataIndex: 'po_no', key: 'po_no', width: 130 },
    { title: '绑定数量', dataIndex: 'bound_qty', key: 'bound_qty', width: 90, render: (v: number) => v?.toLocaleString() },
    { title: '绑定状态', dataIndex: 'bind_status', key: 'bind_status', width: 90, render: (v: string) => <Tag color={v === 'bound' ? 'green' : 'orange'}>{v}</Tag> },
    { title: '绑定来源', dataIndex: 'bind_source', key: 'bind_source', width: 90 },
    {
      title: 'PO状态', key: 'po_status', width: 90,
      render: (_: any, r: any) => r.po_detail ? <StatusTag status={r.po_detail.po_status} /> : '-',
    },
    {
      title: 'ETA', key: 'eta', width: 105,
      render: (_: any, r: any) => {
        const eta = r.po_detail?.eta
        if (!eta) return '-'
        const today = new Date().toISOString().slice(0, 10)
        const overdue = eta < today
        return <span style={{ color: overdue ? '#e11d48' : undefined, fontWeight: overdue ? 600 : undefined }}>{eta}</span>
      },
    },
    {
      title: '供应商', key: 'supplier', width: 120, ellipsis: true,
      render: (_: any, r: any) => r.po_detail?.supplier_name || '-',
    },
  ]

  const issueColumns = [
    { title: '异常号', dataIndex: 'issue_no', key: 'issue_no', width: 100 },
    { title: '类型', dataIndex: 'issue_type', key: 'issue_type', width: 100, render: (v: string) => <Tag>{v}</Tag> },
    { title: '风险', dataIndex: 'risk_level', key: 'risk_level', width: 90, render: (v: string) => <RiskBadge level={v} /> },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    { title: '责任人', dataIndex: 'owner', key: 'owner', width: 90 },
    { title: '承诺日期', dataIndex: 'commit_date', key: 'commit_date', width: 105 },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90, render: (v: string) => <StatusTag status={v} /> },
  ]

  const productColumns = [
    { title: '行号', dataIndex: 'line_no', key: 'line_no', width: 80 },
    { title: '产品编码', dataIndex: 'product_code', key: 'product_code', width: 130 },
    { title: '产品名称', dataIndex: 'product_name', key: 'product_name', ellipsis: true },
    { title: '产品型号', dataIndex: 'product_model', key: 'product_model', width: 130, ellipsis: true },
    { title: '订单数量', dataIndex: 'order_qty', key: 'order_qty', width: 90, render: (v: number | null) => v?.toLocaleString() || '-' },
    { title: '交期', dataIndex: 'promised_date', key: 'promised_date', width: 105 },
    {
      title: '齐套率', dataIndex: 'kit_rate', key: 'kit_rate', width: 90,
      render: (v: number) => {
        const percent = Math.round((v || 0) * 100)
        const color = percent >= 100 ? '#16a34a' : percent >= 80 ? '#f59e0b' : '#e11d48'
        return <span style={{ color, fontWeight: 700 }}>{percent}%</span>
      },
    },
    { title: '物料数', dataIndex: 'total_materials', key: 'total_materials', width: 80 },
    {
      title: '未下单', dataIndex: 'not_ordered_count', key: 'not_ordered_count', width: 80,
      render: (v: number) => v > 0 ? <span style={{ color: '#e11d48', fontWeight: 600 }}>{v}</span> : <span style={{ color: '#94a3b8' }}>0</span>,
    },
    {
      title: '欠料', dataIndex: 'shortage_count', key: 'shortage_count', width: 80,
      render: (v: number) => v > 0 ? <span style={{ color: '#e11d48', fontWeight: 600 }}>{v}</span> : <span style={{ color: '#16a34a' }}>0</span>,
    },
    {
      title: '逾期', dataIndex: 'overdue_count', key: 'overdue_count', width: 80,
      render: (v: number) => v > 0 ? <span style={{ color: '#e11d48', fontWeight: 600 }}>{v}</span> : <span style={{ color: '#94a3b8' }}>0</span>,
    },
    { title: '已到齐', dataIndex: 'arrived_count', key: 'arrived_count', width: 80 },
  ]

  const productMaterialColumns = [
    { title: '物料编码', dataIndex: 'material_code', key: 'material_code', width: 130 },
    { title: '物料名称', dataIndex: 'material_name', key: 'material_name', width: 180, ellipsis: true },
    { title: '规格型号', dataIndex: 'spec_model', key: 'spec_model', width: 140, ellipsis: true },
    { title: '属性', dataIndex: 'material_property_label', key: 'material_property_label', width: 100, render: (v: string | null) => v || '-' },
    { title: '物料分类', dataIndex: 'material_type', key: 'material_type', width: 110, ellipsis: true },
    { title: '需求量', dataIndex: 'req_qty', key: 'req_qty', width: 90, render: (v: number | null, r: ProductMaterialItem) => v != null ? `${v}${r.unit || ''}` : '-' },
    { title: '已分配', dataIndex: 'allocated_qty', key: 'allocated_qty', width: 90 },
    {
      title: '欠料量', dataIndex: 'shortage_qty', key: 'shortage_qty', width: 90,
      render: (v: number) => v > 0 ? <span style={{ color: '#e11d48', fontWeight: 600 }}>{v}</span> : <span style={{ color: '#16a34a' }}>0</span>,
    },
    { title: '需求日期', dataIndex: 'req_date', key: 'req_date', width: 105 },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 120,
      render: (v: string, r: ProductMaterialItem) => <Tag color={STATUS_COLOR[v] || 'default'}>{r.status_label || v}</Tag>,
    },
    { title: 'PO号', dataIndex: 'po_no', key: 'po_no', width: 150, ellipsis: true, render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span> },
    { title: '供应商', dataIndex: 'supplier_name', key: 'supplier_name', width: 130, ellipsis: true, render: (v: string | null) => v || '-' },
    { title: '采购量', dataIndex: 'po_qty', key: 'po_qty', width: 90, render: (v: number | null) => v ?? '-' },
    { title: '收料量', dataIndex: 'received_qty', key: 'received_qty', width: 90, render: (v: number | null) => v ?? 0 },
    { title: 'ETA', dataIndex: 'eta', key: 'eta', width: 105, render: (v: string | null, r: ProductMaterialItem) => v ? <span style={{ color: r.status === 'overdue' ? '#e11d48' : undefined, fontWeight: r.status === 'overdue' ? 600 : undefined }}>{v}</span> : '-' },
    { title: '实际到料', dataIndex: 'actual_arrival_date', key: 'actual_arrival_date', width: 105, render: (v: string | null) => v || '-' },
    { title: '检验日期', dataIndex: 'inspection_date', key: 'inspection_date', width: 105, render: (v: string | null) => v || '-' },
  ]

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/orders')} />
          <div>
            <h2 style={{ marginBottom: 0, fontSize: 18, fontWeight: 700 }}>{detail.order_no} / 行 {detail.line_no || '-'}</h2>
          </div>
        </div>
        <RiskBadge level={detail.risk_level} />
      </div>

      {/* 订单基本信息 */}
      <div className="card-modern" style={{ padding: 20, marginBottom: 16 }}>
        <Descriptions column={{ xs: 2, sm: 3, md: 4, lg: 5 }} size="small" bordered>
          <Descriptions.Item label="客户">{detail.customer || '-'}</Descriptions.Item>
          <Descriptions.Item label="产品">{detail.product_name || '-'}</Descriptions.Item>
          <Descriptions.Item label="产品型号">{detail.product_model || '-'}</Descriptions.Item>
          <Descriptions.Item label="数量">{detail.order_qty?.toLocaleString() || '-'}</Descriptions.Item>
          <Descriptions.Item label="交期">
            <span style={{ color: detail.promised_date && detail.promised_date < new Date().toISOString().slice(0, 10) ? '#e11d48' : undefined, fontWeight: 600 }}>
              {detail.promised_date || '-'}
            </span>
          </Descriptions.Item>
          <Descriptions.Item label="计划开工">{detail.planned_start_date || '-'}</Descriptions.Item>
          <Descriptions.Item label="部门">{detail.department || '-'}</Descriptions.Item>
          <Descriptions.Item label="责任人">{detail.owner || '-'}</Descriptions.Item>
          <Descriptions.Item label="状态"><StatusTag status={detail.status} /></Descriptions.Item>
          <Descriptions.Item label="批号">{detail.batch_no || '-'}</Descriptions.Item>
          <Descriptions.Item label="来源">{detail.data_source || '-'}</Descriptions.Item>
        </Descriptions>
      </div>

      {/* 快速指标 */}
      <Row gutter={[14, 14]} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card size="small" className="card-modern" style={{ textAlign: 'center' }}>
            <ExperimentOutlined style={{ fontSize: 'calc(1.5rem * var(--font-size-scale))', color: '#6366f1' }} />
            <div style={{ fontSize: 'calc(1.75rem * var(--font-size-scale))', fontWeight: 700, color: detail.shortage_count > 0 ? '#e11d48' : '#10b981' }}>{detail.shortage_count}</div>
            <div style={{ color: '#64748b', fontSize: 'calc(0.8125rem * var(--font-size-scale))' }}>欠料项</div>
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small" className="card-modern" style={{ textAlign: 'center' }}>
            <ShoppingCartOutlined style={{ fontSize: 'calc(1.5rem * var(--font-size-scale))', color: '#0ea5e9' }} />
            <div style={{ fontSize: 'calc(1.75rem * var(--font-size-scale))', fontWeight: 700 }}>{detail.in_transit_count}</div>
            <div style={{ color: '#64748b', fontSize: 'calc(0.8125rem * var(--font-size-scale))' }}>在途PO</div>
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small" className="card-modern" style={{ textAlign: 'center' }}>
            <WarningOutlined style={{ fontSize: 'calc(1.5rem * var(--font-size-scale))', color: '#d97706' }} />
            <div style={{ fontSize: 'calc(1.75rem * var(--font-size-scale))', fontWeight: 700 }}>{detail.latest_eta || '-'}</div>
            <div style={{ color: '#64748b', fontSize: 'calc(0.8125rem * var(--font-size-scale))' }}>最晚ETA</div>
          </Card>
        </Col>
      </Row>

      {/* 详情Tab */}
      <Tabs
        defaultActiveKey="product-materials"
        type="card"
        items={[
          {
            key: 'product-materials',
            label: '产品物料情况',
            children: (
              <div className="card-modern" style={{ padding: '2px 0 0' }}>
                <div className="table-modern">
                  <Table
                    columns={productColumns}
                    dataSource={productMaterials}
                    rowKey={(row) => row.line_no || row.product_code || 'product'}
                    size="small"
                    loading={productMaterialsLoading}
                    scroll={{ x: 1200 }}
                    pagination={false}
                    locale={{ emptyText: '暂无产品物料数据' }}
                    expandable={{
                      defaultExpandAllRows: true,
                      expandedRowRender: (row: ProductMaterialGroup) => (
                        <Table
                          columns={productMaterialColumns}
                          dataSource={row.materials}
                          rowKey={(item) => `${row.line_no || '-'}-${item.material_code}-${item.po_no || 'no-po'}`}
                          size="small"
                          pagination={false}
                          scroll={{ x: 1500 }}
                          locale={{ emptyText: '暂无物料明细' }}
                        />
                      ),
                    }}
                  />
                </div>
              </div>
            ),
          },
          {
            key: 'materials',
            label: '物料需求',
            children: (
              <div className="card-modern" style={{ padding: '2px 0 0' }}>
                <div className="table-modern">
                  <Table
                    columns={materialColumns}
                    dataSource={detail.material_demands}
                    rowKey="id"
                    size="small"
                    scroll={{ x: 700 }}
                    locale={{ emptyText: '暂无物料需求数据' }}
                    pagination={false}
                  />
                </div>
              </div>
            ),
          },
          {
            key: 'bindings',
            label: '采购绑定',
            children: (
              <div className="card-modern" style={{ padding: '2px 0 0' }}>
                <div className="table-modern">
                  <Table
                    columns={bindingColumns}
                    dataSource={detail.bindings}
                    rowKey="id"
                    size="small"
                    scroll={{ x: 900 }}
                    locale={{ emptyText: '暂无绑定数据' }}
                    pagination={false}
                  />
                </div>
              </div>
            ),
          },
          {
            key: 'issues',
            label: `异常记录 (${detail.issues.length})`,
            children: (
              <div className="card-modern" style={{ padding: '2px 0 0' }}>
                <div className="table-modern">
                  <Table
                    columns={issueColumns}
                    dataSource={detail.issues}
                    rowKey="id"
                    size="small"
                    scroll={{ x: 800 }}
                    locale={{ emptyText: '暂无异常记录' }}
                    pagination={false}
                  />
                </div>
              </div>
            ),
          },
        ]}
      />
    </div>
  )
}
