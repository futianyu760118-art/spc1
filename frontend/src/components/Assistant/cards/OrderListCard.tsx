import React from 'react'
import { Card, Table, Tag } from 'antd'

interface OrderItem {
  order_no: string
  customer: string
  product_name: string
  promised_date: string
  risk_level: string
  owner: string
}

interface Props {
  title: string
  payload: { orders: OrderItem[]; total: number }
}

const riskColorMap: Record<string, string> = {
  red: 'red',
  yellow: 'orange',
  blue: 'blue',
  green: 'green',
}

const riskLabelMap: Record<string, string> = {
  red: '高风险',
  yellow: '中风险',
  blue: '关注',
  green: '正常',
}

const columns = [
  { title: '订单号', dataIndex: 'order_no', key: 'order_no', width: 130 },
  { title: '客户', dataIndex: 'customer', key: 'customer', ellipsis: true, width: 100 },
  { title: '产品', dataIndex: 'product_name', key: 'product_name', ellipsis: true, width: 120 },
  { title: '应交日期', dataIndex: 'promised_date', key: 'promised_date', width: 100 },
  {
    title: '风险',
    dataIndex: 'risk_level',
    key: 'risk_level',
    width: 80,
    render: (v: string) => (
      <Tag color={riskColorMap[v] || 'default'}>{riskLabelMap[v] || v || '-'}</Tag>
    ),
  },
  { title: '负责人', dataIndex: 'owner', key: 'owner', width: 80 },
]

const OrderListCard: React.FC<Props> = ({ title, payload }) => {
  const orders = payload?.orders || []
  const total = payload?.total || orders.length

  return (
    <Card
      size="small"
      title={title}
      extra={total > orders.length ? <span style={{ color: '#999', fontSize: 12 }}>共 {total} 笔</span> : null}
      style={{ marginBottom: 8 }}
    >
      <Table
        dataSource={orders}
        columns={columns}
        rowKey="order_no"
        size="small"
        pagination={false}
        scroll={{ x: 610 }}
      />
    </Card>
  )
}

export default OrderListCard
