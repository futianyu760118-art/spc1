import React from 'react'
import { Card, Row, Col, Statistic } from 'antd'

interface SummaryItem {
  label: string
  value: number
  color?: string
}

interface Props {
  title: string
  payload: { items: SummaryItem[] }
}

const SummaryCard: React.FC<Props> = ({ title, payload }) => {
  const items = payload?.items || []
  return (
    <Card size="small" title={title} style={{ marginBottom: 8 }}>
      <Row gutter={16}>
        {items.map((item, i) => (
          <Col span={Math.floor(24 / Math.max(items.length, 1))} key={i}>
            <Statistic
              title={item.label}
              value={item.value}
              valueStyle={{ color: item.color || '#1890ff', fontSize: 20 }}
            />
          </Col>
        ))}
      </Row>
    </Card>
  )
}

export default SummaryCard
