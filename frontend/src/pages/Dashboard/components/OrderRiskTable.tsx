import { useState } from 'react'
import { Table, Button, Tag, Input, message, Space } from 'antd'
import { useNavigate } from 'react-router-dom'
import { EditOutlined, SaveOutlined, CloseOutlined } from '@ant-design/icons'
import RiskBadge from '../../../components/RiskBadge'

interface OrderRiskTableProps {
  orders: any[]
  loading: boolean
  pagination: { current: number; pageSize: number; total: number }
  onPageChange: (page: number, pageSize: number) => void
  onUpdate?: (record: any, field: string, value: any) => void
}

const dataSourceColors: Record<string, string> = {
  erp: 'blue',
  excel: 'green',
  manual: 'orange',
}

export default function OrderRiskTable({ orders, loading, pagination, onPageChange, onUpdate }: OrderRiskTableProps) {
  const navigate = useNavigate()
  const [editingKey, setEditingKey] = useState<string>('')

  const isEditing = (record: any) => record.key === editingKey

  const edit = (record: any) => {
    setEditingKey(record.key)
  }

  const save = async (record: any, field: string, value: any) => {
    try {
      await onUpdate?.(record, field, value)
      setEditingKey('')
      message.success('更新成功')
    } catch {
      message.error('更新失败')
    }
  }

  const cancel = () => {
    setEditingKey('')
  }

  const columns = [
    { title: '订单号', dataIndex: 'order_no', key: 'order_no', width: 120 },
    { title: '行号', dataIndex: 'line_no', key: 'line_no', width: 70 },
    { title: '客户', dataIndex: 'customer', key: 'customer' },
    { title: '产品', dataIndex: 'product_name', key: 'product_name', ellipsis: true },
    { title: '承诺交期', dataIndex: 'promised_date', key: 'promised_date', width: 110 },
    { title: '计划上线', dataIndex: 'planned_start_date', key: 'planned_start_date', width: 110 },
    { title: '欠料数', dataIndex: 'shortage_count', key: 'shortage_count', width: 80 },
    {
      title: '风险等级',
      dataIndex: 'risk_level',
      key: 'risk_level',
      width: 100,
      render: (level: string) => <RiskBadge level={level} />,
    },
    {
      title: '责任人',
      dataIndex: 'owner',
      key: 'owner',
      width: 120,
      render: (text: string, record: any) => {
        const editable = isEditing(record)
        return editable ? (
          <Input
            defaultValue={text}
            size="small"
            onBlur={(e) => save(record, 'owner', e.target.value)}
            onPressEnter={(e) => save(record, 'owner', (e.target as HTMLInputElement).value)}
          />
        ) : (
          <span>{text}</span>
        )
      },
    },
    {
      title: '数据来源',
      dataIndex: 'data_source',
      key: 'data_source',
      width: 100,
      render: (source: string) => (
        <Tag color={dataSourceColors[source] || 'default'} style={{ fontSize: 11 }}>
          {source?.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      fixed: 'right' as const,
      render: (_: any, record: any) => {
        const editable = isEditing(record)
        return editable ? (
          <Space size="small">
            <Button size="small" icon={<SaveOutlined />} type="primary" onClick={() => save(record, 'owner', record.owner)} />
            <Button size="small" icon={<CloseOutlined />} onClick={cancel} />
          </Space>
        ) : (
          <Space size="small">
            <Button type="link" size="small" style={{ padding: 0 }} onClick={() => navigate(`/orders/${record.order_no}`)}>
              详情
            </Button>
            <Button size="small" icon={<EditOutlined />} onClick={() => edit(record)} />
          </Space>
        )
      },
    },
  ]

  return (
    <div className="card-modern" style={{ padding: '2px 0 0' }}>
      <div className="table-modern">
        <Table
          columns={columns}
          dataSource={orders}
          rowKey={(r) => `${r.order_no}-${r.line_no}`}
          loading={loading}
          size="middle"
          scroll={{ x: 1300, y: 'calc(100vh - 340px)' }}
          locale={{ emptyText: '暂无订单风险数据，请先导入数据或触发风险扫描' }}
          pagination={{
            ...pagination,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
            onChange: onPageChange,
            style: { padding: '0 16px' },
          }}
        />
      </div>
    </div>
  )
}
