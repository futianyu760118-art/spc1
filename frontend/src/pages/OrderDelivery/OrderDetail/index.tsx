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

export default function OrderDetail() {
  const { orderNo, lineNo } = useParams<{ orderNo: string; lineNo: string }>()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<OrderDetailData | null>(null)
  const [loading, setLoading] = useState(true)
  const [etaHistory, setEtaHistory] = useState<any[]>([])

  const fetchDetail = async () => {
    if (!orderNo) return
    setLoading(true)
    try {
      const res: any = await orderApi.getDetail(orderNo, lineNo)
      setDetail(res.data)
    } catch {
      message.error('获取订单详情失败')
    } finally {
      setLoading(false)
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
            <ExperimentOutlined style={{ fontSize: 24, color: '#6366f1' }} />
            <div style={{ fontSize: 28, fontWeight: 700, color: detail.shortage_count > 0 ? '#e11d48' : '#10b981' }}>{detail.shortage_count}</div>
            <div style={{ color: '#64748b', fontSize: 13 }}>欠料项</div>
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small" className="card-modern" style={{ textAlign: 'center' }}>
            <ShoppingCartOutlined style={{ fontSize: 24, color: '#0ea5e9' }} />
            <div style={{ fontSize: 28, fontWeight: 700 }}>{detail.in_transit_count}</div>
            <div style={{ color: '#64748b', fontSize: 13 }}>在途PO</div>
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small" className="card-modern" style={{ textAlign: 'center' }}>
            <WarningOutlined style={{ fontSize: 24, color: '#d97706' }} />
            <div style={{ fontSize: 28, fontWeight: 700 }}>{detail.latest_eta || '-'}</div>
            <div style={{ color: '#64748b', fontSize: 13 }}>最晚ETA</div>
          </Card>
        </Col>
      </Row>

      {/* 详情Tab */}
      <Tabs
        defaultActiveKey="materials"
        type="card"
        items={[
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
