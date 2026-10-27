import React, { useCallback, useEffect, useState } from 'react'
import { Button, Card, Col, DatePicker, Input, Row, Select, Space, Statistic, Table, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
import { agentApi, AgentTask, AgentTaskSummary } from '../../../services/agent'
import { TaskAnalysisTag, TaskPriorityTag, TaskStatusTag } from '../../../components/Agent/TaskStatusTag'

const { Text } = Typography

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'pending', label: '待处理' },
  { value: 'in_progress', label: '处理中' },
  { value: 'blocked', label: '阻塞' },
  { value: 'completed', label: '已完成' },
  { value: 'cancelled', label: '已取消' },
]

export default function MyTasks() {
  const navigate = useNavigate()
  const [rows, setRows] = useState<AgentTask[]>([])
  const [total, setTotal] = useState(0)
  const [summary, setSummary] = useState<AgentTaskSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [keyword, setKeyword] = useState('')
  const [dueRange, setDueRange] = useState<any>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [list, sum]: any = await Promise.all([
        agentApi.myTasks({
          status, priority, keyword, page, page_size: pageSize,
          due_from: dueRange?.[0] ? dueRange[0].startOf('day').format('YYYY-MM-DDTHH:mm:ss') : undefined,
          due_to: dueRange?.[1] ? dueRange[1].endOf('day').format('YYYY-MM-DDTHH:mm:ss') : undefined,
        }),
        agentApi.myTasksSummary(),
      ])
      setRows(list.data?.items || [])
      setTotal(list.data?.total || 0)
      setSummary(sum.data || null)
    } finally {
      setLoading(false)
    }
  }, [status, priority, keyword, dueRange, page, pageSize])

  useEffect(() => { load() }, [load])

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Row gutter={16}>
        <Col span={6}><Card><Statistic title="未完成" value={summary?.open || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="逾期" value={summary?.overdue || 0} valueStyle={{ color: '#dc2626' }} /></Card></Col>
        <Col span={6}><Card><Statistic title="阻塞" value={summary?.by_status?.blocked || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="近 7 天完成" value={summary?.completed_week || 0} /></Card></Col>
      </Row>

      <Card>
        <Space wrap style={{ marginBottom: 16 }}>
          <Select value={status} onChange={v => { setStatus(v); setPage(1) }} options={STATUS_OPTIONS} style={{ width: 140 }} />
          <Select
            value={priority}
            onChange={v => { setPriority(v); setPage(1) }}
            style={{ width: 140 }}
            options={[
              { value: '', label: '全部优先级' },
              { value: 'urgent', label: '紧急' },
              { value: 'high', label: '高' },
              { value: 'normal', label: '普通' },
              { value: 'low', label: '低' },
            ]}
          />
          <Input.Search
            placeholder="任务号 / 标题 / 业务单号"
            allowClear
            style={{ width: 260 }}
            onSearch={v => { setKeyword(v); setPage(1) }}
          />
          <DatePicker.RangePicker
            value={dueRange}
            onChange={value => { setDueRange(value); setPage(1) }}
            placeholder={['截止起', '截止止']}
          />
          <Button onClick={load}>刷新</Button>
        </Space>

        <Table
          size="small"
          rowKey="id"
          loading={loading}
          dataSource={rows}
          pagination={{
            current: page, pageSize, total, showSizeChanger: true,
            onChange: (p, s) => { setPage(p); setPageSize(s) },
          }}
          onRow={record => ({ onClick: () => navigate(`/agents/tasks/${record.id}`), style: { cursor: 'pointer' } })}
          columns={[
            { title: '任务号', dataIndex: 'task_no', width: 110 },
            {
              title: '标题', dataIndex: 'title',
              render: (v: string, row: AgentTask) => (
                <div>
                  <div style={{ fontWeight: 500 }}>{v}</div>
                  {row.biz_title && <Text type="secondary" style={{ fontSize: 12 }}>{row.biz_title}</Text>}
                </div>
              ),
            },
            { title: '派发人', dataIndex: 'assigner_name', width: 110, render: (v: string) => v || '-' },
            {
              title: '截止', dataIndex: 'due_at', width: 160,
              render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-',
            },
            { title: '优先级', dataIndex: 'priority', width: 90, render: (v: any) => <TaskPriorityTag priority={v} /> },
            {
              title: '状态', dataIndex: 'status', width: 150,
              render: (v: any, row: AgentTask) => <TaskStatusTag status={v} isOverdue={row.is_overdue} />,
            },
            { title: '分析', dataIndex: 'analysis_status', width: 100, render: (v: any) => <TaskAnalysisTag status={v} /> },
          ]}
        />
      </Card>
    </Space>
  )
}
