import { Modal, Button, Row, Col, Progress, Tooltip } from 'antd'
import { WarningOutlined } from '@ant-design/icons'
import RiskBadge from './RiskBadge'
import { formatDateTime } from '../utils'

const FACTOR_LABELS: Record<string, string> = {
  delivery_delay: '交期延期',
  shortage: '欠料风险',
  process_lag: '工序滞后',
  quality: '品质异常',
  eta_delay: 'ETA延期',
  inspection_ng: '客检NG',
}

const FACTOR_MAX: Record<string, number> = {
  delivery_delay: 25,
  shortage: 30,
  process_lag: 15,
  quality: 15,
  eta_delay: 20,
  inspection_ng: 15,
}

const FACTOR_DESCRIPTIONS: Record<string, string> = {
  delivery_delay: '订单交期已延期或即将延期，可能导致客户投诉或违约风险',
  shortage: '物料存在欠料情况，可能影响生产进度和交期',
  process_lag: '生产工序进度滞后，可能影响整体生产计划',
  quality: '存在品质异常问题，可能导致返工或报废',
  eta_delay: '采购物料ETA（预计到货时间）已延期，影响物料齐套',
  inspection_ng: '客户检验不通过（NG），需要重新整改或返工',
}

interface RiskOrder {
  order_no: string
  risk_level: string | null
  risk_score: number | null
  risk_factors: Record<string, number> | null
  risk_assessed_at: string | null
}

interface RiskDetailModalProps {
  visible: boolean
  order: RiskOrder | null
  onClose: () => void
}

export default function RiskDetailModal({ visible, order, onClose }: RiskDetailModalProps) {
  return (
    <Modal
      title={<span><WarningOutlined style={{ marginRight: 8 }} />风险详情 — {order?.order_no}</span>}
      open={visible}
      onCancel={onClose}
      width={640}
      footer={[
        <Button key="close" onClick={onClose}>关闭</Button>,
      ]}
    >
      {order?.risk_factors ? (
        <div>
          <div style={{ marginBottom: 16, padding: '12px', background: '#f8fafc', borderRadius: 8 }}>
            <Row gutter={16}>
              <Col span={8}>
                <span style={{ color: '#64748b', fontSize: 12 }}>风险等级</span>
                <div style={{ marginTop: 4 }}><RiskBadge level={order.risk_level} /></div>
              </Col>
              <Col span={8}>
                <span style={{ color: '#64748b', fontSize: 12 }}>风险评分</span>
                <div style={{ marginTop: 4, fontSize: 18, fontWeight: 700, color: order.risk_score && order.risk_score >= 60 ? '#e11d48' : order.risk_score && order.risk_score >= 30 ? '#f59e0b' : '#10b981' }}>
                  {order.risk_score ?? '-'}
                </div>
              </Col>
              <Col span={8}>
                <span style={{ color: '#64748b', fontSize: 12 }}>评估时间</span>
                <div style={{ marginTop: 4, fontSize: 12 }}>{formatDateTime(order.risk_assessed_at)}</div>
              </Col>
            </Row>
          </div>

          {/* 评分依据说明 */}
          <div style={{ marginBottom: 16, padding: '12px', background: '#fef3c7', borderRadius: 8, border: '1px solid #fcd34d' }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#92400e', marginBottom: 8 }}>评分依据</div>
            <div style={{ fontSize: 11, color: '#78350f', lineHeight: 1.6 }}>
              <div style={{ marginBottom: 4 }}>风险评分基于6个评分因子的总和（满分100分）：</div>
              <div style={{ marginBottom: 4 }}>• 交期延期（25分）、欠料风险（30分）、ETA延期（20分）、工序滞后（15分）、品质异常（15分）、客检NG（15分）</div>
              <div>风险等级判定：红色≥60分（高风险）、黄色30-59分（中风险）、蓝色1-29分（低风险）、绿色0分（正常）</div>
            </div>
          </div>

          <div style={{ fontSize: 13, fontWeight: 600, color: '#475569', marginBottom: 12 }}>风险因子详情</div>
          <Row gutter={[16, 12]}>
            {Object.entries(FACTOR_LABELS).map(([key, label]) => {
              const val = order.risk_factors?.[key] || 0
              const max = FACTOR_MAX[key] || 1
              const pct = Math.round(val / max * 100)
              const color = val >= max * 0.6 ? '#e11d48' : val >= max * 0.3 ? '#f59e0b' : '#10b981'
              const description = FACTOR_DESCRIPTIONS[key] || ''
              return (
                <Col span={12} key={key}>
                  <Tooltip title={description} placement="top">
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4, cursor: 'help' }}>
                      <span style={{ fontSize: 12, color: '#64748b' }}>{label}</span>
                      <span style={{ fontSize: 12, fontWeight: 600, color }}>{val}/{max}</span>
                    </div>
                    <Progress percent={pct} strokeColor={color} showInfo={false} style={{ marginBottom: 0 }} />
                  </Tooltip>
                </Col>
              )
            })}
          </Row>
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: 24, color: '#94a3b8' }}>暂无风险评估数据</div>
      )}
    </Modal>
  )
}
