import { Table, Button, Tag } from 'antd'
import StatusTag from '../../../../components/StatusTag'

const issueTypeMap: Record<string, { label: string; color: string }> = {
  delivery_delay: { label: '交期延期', color: 'blue' },
  shortage: { label: '欠料风险', color: 'blue' },
  eta_delay: { label: 'ETA延期', color: 'blue' },
  process_lag: { label: '工序滞后', color: 'blue' },
  quality: { label: '品质异常', color: 'blue' },
  inspection_ng: { label: '客检NG', color: 'blue' },
  holiday_risk: { label: '假期风险', color: 'green' },
  long_lead: { label: '长周期物料', color: 'green' },
}

interface IssueTableProps {
  data: any[]
  loading: boolean
  pagination: { current: number; pageSize: number; total: number }
  onPageChange: (page: number, pageSize: number) => void
  onEdit: (record: any) => void
}

export default function IssueTable({ data, loading, pagination, onPageChange, onEdit }: IssueTableProps) {
  const columns = [
    { title: '问题编号', dataIndex: 'issue_no', key: 'issue_no', width: 130 },
    {
      title: '类型',
      dataIndex: 'issue_type',
      key: 'issue_type',
      render: (t: string) => {
        const m = issueTypeMap[t]
        return m ? <Tag color={m.color}>{m.label}</Tag> : <Tag>{t}</Tag>
      },
    },
    {
      title: '风险',
      dataIndex: 'risk_level',
      key: 'risk_level',
      render: (l: string) => <Tag color={l === 'red' ? 'red' : 'orange'}>{l === 'red' ? '高' : '中'}</Tag>,
    },
    { title: '订单号', dataIndex: 'order_no', key: 'order_no' },
    { title: '物料', dataIndex: 'material_code', key: 'material_code' },
    { title: 'PO', dataIndex: 'po_no', key: 'po_no' },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    { title: '责任人', dataIndex: 'owner', key: 'owner' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => <StatusTag status={s} />,
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 170 },
    {
      title: '操作',
      key: 'action',
      width: 80,
      fixed: 'right' as const,
      render: (_: any, record: any) => (
        <Button size="small" onClick={() => onEdit(record)}>处置</Button>
      ),
    },
  ]

  return (
    <div className="card-modern" style={{ padding: '2px 0 0' }}>
      <div className="table-modern">
        <Table
          columns={columns}
          dataSource={data}
          rowKey="id"
          loading={loading}
          size="middle"
          scroll={{ x: 1200, y: 'calc(100vh - 320px)' }}
          locale={{ emptyText: '暂无异常问题记录，系统将在风险扫描后自动生成，也可手动新建' }}
          pagination={{
            ...pagination,
            showSizeChanger: true,
            showTotal: (total: number) => `共 ${total} 条`,
            onChange: onPageChange,
            style: { padding: '0 16px' },
          }}
        />
      </div>
    </div>
  )
}
