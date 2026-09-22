import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Select, Space, Table, Tag } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { approvalApi, type ApprovalPendingItem } from '../../../services/approval'

export default function ApprovalPending() {
  const navigate = useNavigate()
  const [items, setItems] = useState<ApprovalPendingItem[]>([])
  const [loading, setLoading] = useState(false)
  const [bizType, setBizType] = useState<string | undefined>(undefined)

  const load = async () => {
    setLoading(true)
    try {
      const res: any = await approvalApi.pending()
      setItems(res.data || [])
    } catch { /* 全局拦截器已提示 */ } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const bizOptions = useMemo(() => {
    const seen = new Map<string, string>()
    items.forEach(i => { if (!seen.has(i.biz_type)) seen.set(i.biz_type, i.biz_name || i.biz_type) })
    return Array.from(seen, ([value, label]) => ({ value, label }))
  }, [items])

  const dataSource = bizType ? items.filter(i => i.biz_type === bizType) : items

  return (
    <Card title="待我审批" extra={
      <Space>
        <Select allowClear placeholder="全部业务类型" style={{ width: 200 }} value={bizType}
          onChange={setBizType} options={bizOptions} />
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </Space>
    }>
      <Table<ApprovalPendingItem> rowKey={r => `${r.biz_type}-${r.id}`} loading={loading} dataSource={dataSource}
        scroll={{ x: 1200 }}
        locale={{ emptyText: '暂无待您审批的单据' }}
        columns={[
          { title: '业务类型', dataIndex: 'biz_type', width: 140, render: (_: any, r: ApprovalPendingItem) => <Tag color="blue">{r.biz_name || r.biz_type}</Tag> },
          { title: '单号', dataIndex: 'no', width: 180, render: (_: any, r: ApprovalPendingItem) => (
            <a style={{ fontFamily: 'monospace', fontWeight: 600 }} onClick={() => navigate(r.deep_link)}>{r.no || '-'}</a>
          ) },
          { title: '标题', dataIndex: 'title', ellipsis: true, render: (v: string) => v || '-' },
          { title: '摘要', dataIndex: 'summary', ellipsis: true, render: (v: string) => v || '-' },
          { title: '申请人', dataIndex: 'applicant', width: 110, render: (v: string) => v || '-' },
          { title: '提交时间', dataIndex: 'submitted_at', width: 160, render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-' },
          { title: '当前节点', dataIndex: 'current_node', width: 140, render: (_: any, r: ApprovalPendingItem) => r.current_node || (r.current_level ? `L${r.current_level}` : '-') },
          { title: '操作', width: 100, fixed: 'right', render: (_: any, r: ApprovalPendingItem) => (
            <Button size="small" type="primary" onClick={() => navigate(r.deep_link)}>去审批</Button>
          ) },
        ]} />
    </Card>
  )
}
