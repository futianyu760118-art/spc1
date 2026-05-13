import { Row, Col, Progress, Table, Tag, Tooltip } from 'antd'
import {
  LinkOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons'

interface KPIIndicator {
  label: string
  value: number
  target: number
  status: string
}

interface MaterialShortageRow {
  material_code: string
  material_name: string | null
  total_req_qty: number
  total_allocated_qty: number
  shortage_qty: number
  affected_orders: number
}

interface KPICardsProps {
  kpis: KPIIndicator[]
  shortageTop: MaterialShortageRow[]
}

const statusColors: Record<string, string> = {
  normal: '#10b981',
  warning: '#f59e0b',
  danger: '#e11d48',
}

const kpiIcons = [
  <LinkOutlined style={{ fontSize: 20 }} />,
  <CheckCircleOutlined style={{ fontSize: 20 }} />,
  <ClockCircleOutlined style={{ fontSize: 20 }} />,
]

const kpiDescriptions: Record<string, string> = {
  '绑定覆盖率': '销售订单的物料需求与采购订单绑定的覆盖程度',
  '物料齐套率': '物料需求中已齐套可满足订单生产的比例（1 - 欠料率）',
  'ETA及时率': '未完成采购订单中已填写预计到货时间的比例',
}

const shortageColumns = [
  { title: '物料编码', dataIndex: 'material_code', key: 'material_code', width: 120 },
  { title: '物料名称', dataIndex: 'material_name', key: 'material_name', ellipsis: true },
  {
    title: '需求量', dataIndex: 'total_req_qty', key: 'total_req_qty', width: 90,
    render: (v: number) => v?.toLocaleString(),
  },
  {
    title: '已分配', dataIndex: 'total_allocated_qty', key: 'total_allocated_qty', width: 90,
    render: (v: number) => v?.toLocaleString(),
  },
  {
    title: '欠料量', dataIndex: 'shortage_qty', key: 'shortage_qty', width: 90,
    render: (v: number) => <span style={{ color: '#e11d48', fontWeight: 600 }}>{v?.toLocaleString()}</span>,
  },
  {
    title: '影响订单', dataIndex: 'affected_orders', key: 'affected_orders', width: 90,
    render: (v: number) => <Tag color="red">{v}</Tag>,
  },
]

export default function KPICards({ kpis, shortageTop }: KPICardsProps) {
  return (
    <Row gutter={[14, 14]} style={{ marginBottom: 18 }}>
      {/* KPI 指标卡 */}
      <Col xs={24} md={8}>
        <div className="card-modern" style={{ padding: '20px 24px', height: '100%' }}>
          <h3 className="text-sm font-semibold m-0 mb-4" style={{ color: '#475569' }}>核心 KPI</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {kpis.map((kpi, idx) => {
              const pct = Math.round(kpi.value * 100)
              const targetPct = Math.round(kpi.target * 100)
              return (
                <div key={kpi.label}>
                  <div className="flex items-center justify-between" style={{ marginBottom: 6 }}>
                    <div className="flex items-center gap-2">
                      <span style={{ color: statusColors[kpi.status] }}>{kpiIcons[idx]}</span>
                      <span style={{ fontSize: 13, fontWeight: 500, color: '#334155' }}>{kpi.label}</span>
                      <Tooltip title={kpiDescriptions[kpi.label]} placement="top">
                        <QuestionCircleOutlined style={{ fontSize: 12, color: '#94a3b8', cursor: 'help' }} />
                      </Tooltip>
                    </div>
                    <div>
                      <span style={{ fontSize: 18, fontWeight: 700, color: statusColors[kpi.status] }}>{pct}%</span>
                      <span style={{ fontSize: 11, color: '#94a3b8', marginLeft: 6 }}>目标 {targetPct}%</span>
                    </div>
                  </div>
                  <Progress
                    percent={pct}
                    showInfo={false}
                    strokeColor={statusColors[kpi.status]}
                    trailColor="#f1f5f9"
                    size="small"
                  />
                </div>
              )
            })}
          </div>
        </div>
      </Col>

      {/* 欠料 TOP 10 */}
      <Col xs={24} md={16}>
        <div className="card-modern" style={{ padding: '20px 24px', height: '100%' }}>
          <h3 className="text-sm font-semibold m-0 mb-3" style={{ color: '#475569' }}>欠料 TOP 10</h3>
          {shortageTop.length > 0 ? (
            <Table
              columns={shortageColumns}
              dataSource={shortageTop}
              rowKey="material_code"
              size="small"
              pagination={false}
              scroll={{ y: 220 }}
            />
          ) : (
            <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>
              暂无欠料数据
            </div>
          )}
        </div>
      </Col>
    </Row>
  )
}
