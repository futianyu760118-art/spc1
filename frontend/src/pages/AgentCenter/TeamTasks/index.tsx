import React, { useCallback, useEffect, useState } from 'react'
import {
  Button, Card, Col, DatePicker, Dropdown, Input, Modal, Row, Select, Space, Statistic, Table, Tag, Typography, message,
} from 'antd'
import { MoreOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import { agentApi, AgentTask, TeamTaskSummary } from '../../../services/agent'
import { TaskAnalysisTag, TaskPriorityTag, TaskStatusTag } from '../../../components/Agent/TaskStatusTag'

const { Text } = Typography

export default function TeamTasks() {
  const navigate = useNavigate()
  const [rows, setRows] = useState<AgentTask[]>([])
  const [summary, setSummary] = useState<TeamTaskSummary | null>(null)
  const [children, setChildren] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [assignee, setAssignee] = useState<number | undefined>()
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const [cancelTask, setCancelTask] = useState<AgentTask | null>(null)
  const [cancelReason, setCancelReason] = useState('')
  const [returnTask, setReturnTask] = useState<AgentTask | null>(null)
  const [returnReason, setReturnReason] = useState('')
  const [reassignTask, setReassignTask] = useState<AgentTask | null>(null)
  const [reassignUser, setReassignUser] = useState<number | null>(null)
  const [updateTask, setUpdateTask] = useState<AgentTask | null>(null)
  const [updateDue, setUpdateDue] = useState<any>(null)
  const [updatePriority, setUpdatePriority] = useState<string>('normal')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [list, sum, team]: any = await Promise.all([
        agentApi.teamTasks({ status, keyword, assignee_user_id: assignee, page, page_size: pageSize }),
        agentApi.teamTasksSummary(),
        agentApi.team(),
      ])
      setRows(list.data?.items || [])
      setTotal(list.data?.total || 0)
      setSummary(sum.data || null)
      setChildren(team.data?.items || [])
    } finally {
      setLoading(false)
    }
  }, [status, keyword, assignee, page, pageSize])

  useEffect(() => { load() }, [load])

  const refresh = () => load()

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Row gutter={16}>
        <Col span={5}><Card><Statistic title="未完成" value={summary?.open || 0} /></Card></Col>
        <Col span={5}><Card><Statistic title="逾期" value={summary?.overdue || 0} valueStyle={{ color: '#dc2626' }} /></Card></Col>
        <Col span={5}><Card><Statistic title="阻塞" value={summary?.blocked || 0} /></Card></Col>
        <Col span={5}><Card><Statistic title="近 7 天完成" value={summary?.completed_week || 0} /></Card></Col>
        <Col span={4}><Card><Statistic title="分析失败" value={summary?.analysis_failed || 0} /></Card></Col>
      </Row>

      <Card title="按人负载" size="small">
        <Space wrap>
          {(summary?.by_assignee || []).map(item => (
            <Tag key={item.assignee_user_id} color={item.overdue ? 'red' : item.open ? 'blue' : 'default'}>
              {item.assignee_name || item.assignee_user_id}：未完成 {item.open} / 逾期 {item.overdue}
            </Tag>
          ))}
        </Space>
      </Card>

      <Card>
        <Space wrap style={{ marginBottom: 16 }}>
          <Select
            value={status} style={{ width: 140 }}
            onChange={v => { setStatus(v); setPage(1) }}
            options={[
              { value: '', label: '全部状态' },
              { value: 'pending', label: '待处理' },
              { value: 'in_progress', label: '处理中' },
              { value: 'blocked', label: '阻塞' },
              { value: 'completed', label: '已完成' },
              { value: 'cancelled', label: '已取消' },
            ]}
          />
          <Select
            allowClear placeholder="按接收人" style={{ width: 160 }}
            value={assignee}
            onChange={v => { setAssignee(v); setPage(1) }}
            options={children.map(c => ({ value: c.user_id, label: c.name || c.username }))}
          />
          <Input.Search
            placeholder="任务号 / 标题 / 业务单号" allowClear style={{ width: 260 }}
            onSearch={v => { setKeyword(v); setPage(1) }}
          />
          <Button onClick={refresh}>刷新</Button>
        </Space>

        <Table
          size="small" rowKey="id" loading={loading} dataSource={rows}
          pagination={{ current: page, pageSize, total, showSizeChanger: true, onChange: (p, s) => { setPage(p); setPageSize(s) } }}
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
            { title: '接收人', dataIndex: 'assignee_name', width: 120, render: (v: string) => v || '-' },
            { title: '截止', dataIndex: 'due_at', width: 160, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-' },
            { title: '优先级', dataIndex: 'priority', width: 90, render: (v: any) => <TaskPriorityTag priority={v} /> },
            { title: '状态', dataIndex: 'status', width: 150, render: (v: any, row: AgentTask) => <TaskStatusTag status={v} isOverdue={row.is_overdue} /> },
            { title: '分析', dataIndex: 'analysis_status', width: 100, render: (v: any) => <TaskAnalysisTag status={v} /> },
            {
              title: '最新汇报', dataIndex: 'latest_report', width: 220,
              render: (report: any) => report?.summary
                ? <Text ellipsis={{ tooltip: report.summary }} style={{ maxWidth: 200 }}>v{report.version} {report.summary}</Text>
                : <Text type="secondary">-</Text>,
            },
            {
              title: '操作', width: 80, fixed: 'right' as const,
              render: (_: any, row: AgentTask) => (
                <div onClick={e => e.stopPropagation()}>
                  <Dropdown
                    menu={{
                      items: [
                        { key: 'remind', label: '催办' },
                        { key: 'update', label: '改期/优先级', disabled: ['completed', 'cancelled'].includes(row.status) },
                        { key: 'reassign', label: '改派', disabled: ['completed', 'cancelled'].includes(row.status) },
                        { key: 'cancel', label: '取消', danger: true, disabled: ['completed', 'cancelled'].includes(row.status) },
                        { key: 'return', label: '退回重做', disabled: row.status !== 'completed' },
                      ],
                      onClick: async ({ key }) => {
                        if (key === 'remind') {
                          await agentApi.remindTask(row.id); message.success('已催办'); refresh()
                        } else if (key === 'update') {
                          setUpdateTask(row)
                          setUpdateDue(row.due_at ? dayjs(row.due_at) : null)
                          setUpdatePriority(row.priority)
                        } else if (key === 'reassign') {
                          setReassignTask(row); setReassignUser(null)
                        } else if (key === 'cancel') {
                          setCancelTask(row); setCancelReason('')
                        } else if (key === 'return') {
                          setReturnTask(row); setReturnReason('')
                        }
                      },
                    }}
                  >
                    <Button size="small" type="text" icon={<MoreOutlined />} />
                  </Dropdown>
                </div>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title="取消任务" open={!!cancelTask} onCancel={() => setCancelTask(null)}
        onOk={async () => {
          if (!cancelTask) return
          if (!cancelReason.trim()) { message.warning('请填写取消原因'); return }
          await agentApi.cancelTask(cancelTask.id, cancelReason)
          message.success('任务已取消'); setCancelTask(null); refresh()
        }}
        okText="确认取消" okButtonProps={{ danger: true }}
      >
        <Input.TextArea rows={3} value={cancelReason} onChange={e => setCancelReason(e.target.value)} placeholder="必填：取消原因" />
      </Modal>

      <Modal
        title="退回重做" open={!!returnTask} onCancel={() => setReturnTask(null)}
        onOk={async () => {
          if (!returnTask) return
          await agentApi.returnTask(returnTask.id, returnReason)
          message.success('任务已退回'); setReturnTask(null); refresh()
        }}
        okText="确认退回"
      >
        <Input.TextArea rows={3} value={returnReason} onChange={e => setReturnReason(e.target.value)} placeholder="退回原因（可选）" />
      </Modal>

      <Modal
        title="改派任务" open={!!reassignTask} onCancel={() => setReassignTask(null)}
        onOk={async () => {
          if (!reassignTask) return
          if (!reassignUser) { message.warning('请选择新接收人'); return }
          await agentApi.reassignTask(reassignTask.id, reassignUser)
          message.success('任务已改派'); setReassignTask(null); refresh()
        }}
        okText="确认改派"
      >
        <Select
          style={{ width: '100%' }} placeholder="选择直属子智能体"
          value={reassignUser || undefined} onChange={setReassignUser}
          options={children.filter(c => c.user_id !== reassignTask?.assignee_user_id).map(c => ({ value: c.user_id, label: c.name || c.username }))}
        />
      </Modal>

      <Modal
        title="修改截止/优先级" open={!!updateTask} onCancel={() => setUpdateTask(null)}
        onOk={async () => {
          if (!updateTask) return
          await agentApi.patchTask(updateTask.id, {
            due_at: updateDue ? dayjs(updateDue).format('YYYY-MM-DDTHH:mm:ss') : undefined,
            priority: updatePriority,
          })
          message.success('任务已更新'); setUpdateTask(null); refresh()
        }}
        okText="保存"
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <DatePicker showTime style={{ width: '100%' }} value={updateDue ? dayjs(updateDue) : null} onChange={setUpdateDue} />
          <Select
            style={{ width: '100%' }} value={updatePriority} onChange={setUpdatePriority}
            options={[
              { value: 'low', label: '低' }, { value: 'normal', label: '普通' },
              { value: 'high', label: '高' }, { value: 'urgent', label: '紧急' },
            ]}
          />
        </Space>
      </Modal>
    </Space>
  )
}
