import React, { useCallback, useEffect, useState } from 'react'
import {
  Alert, Button, Card, Collapse, DatePicker, Descriptions, Divider, Empty, Form, Input, List, Modal, Select, Space, Spin, Tabs, Typography, message,
} from 'antd'
import { useNavigate, useParams } from 'react-router-dom'
import dayjs from 'dayjs'
import { agentApi, AgentTaskDetail } from '../../../services/agent'
import { TaskAnalysisTag, TaskPriorityTag, TaskStatusTag } from '../../../components/Agent/TaskStatusTag'
import { TaskTimeline } from '../../../components/Agent/TaskTimeline'
import { ReportEditor } from '../../../components/Agent/ReportEditor'
import Markdown from '../../../components/Markdown'

const { Text, Title } = Typography

export default function TaskDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const taskId = Number(id)
  const [detail, setDetail] = useState<AgentTaskDetail | null>(null)
  const [taskChat, setTaskChat] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [children, setChildren] = useState<any[]>([])
  const [reportOpen, setReportOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [blockOpen, setBlockOpen] = useState(false)
  const [blockReason, setBlockReason] = useState('')
  const [cancelOpen, setCancelOpen] = useState(false)
  const [cancelReason, setCancelReason] = useState('')
  const [returnOpen, setReturnOpen] = useState(false)
  const [returnReason, setReturnReason] = useState('')
  const [updateOpen, setUpdateOpen] = useState(false)
  const [updateForm] = Form.useForm()
  const [reassignOpen, setReassignOpen] = useState(false)
  const [reassignUserId, setReassignUserId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await agentApi.task(taskId)
      setDetail(res.data)
      try {
        const conv: any = await agentApi.taskConversation(taskId)
        const messages: any = await agentApi.conversation(conv.data.conversation_id)
        setTaskChat(messages.data)
      } catch {
        setTaskChat(null)
      }
      if (res.data?.can_manage) {
        try {
          const team: any = await agentApi.team()
          setChildren(team.data?.items || [])
        } catch {
          setChildren([])
        }
      }
    } finally {
      setLoading(false)
    }
  }, [taskId])

  useEffect(() => { if (taskId) load() }, [taskId, load])

  if (loading && !detail) return <Card><Spin /></Card>
  if (!detail) return <Card><Empty description="任务不存在或无权查看" /></Card>

  const task = detail

  const doAction = async (fn: () => Promise<any>, success: string) => {
    await fn()
    message.success(success)
    await load()
  }

  const openAssistant = async () => {
    try {
      await agentApi.taskConversation(task.id)
    } catch {
      // 会话创建失败不阻断打开（服务端对话时还会校验）
    }
    window.dispatchEvent(new CustomEvent('spc:open-assistant', { detail: { taskId: task.id } }))
  }

  const submitReport = async (data: any) => {
    setSubmitting(true)
    try {
      await doAction(() => agentApi.submitTask(task.id, data), '汇报已提交，任务已完成')
      setReportOpen(false)
    } finally {
      setSubmitting(false)
    }
  }

  const overview = (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Descriptions column={2} size="small" bordered>
        <Descriptions.Item label="任务号">{task.task_no}</Descriptions.Item>
        <Descriptions.Item label="任务类型">{task.task_type === 'business' ? '业务任务' : '通用待办'}</Descriptions.Item>
        <Descriptions.Item label="派发人">{task.assigner_name || task.assigner_user_id}</Descriptions.Item>
        <Descriptions.Item label="接收人">{task.assignee_name || task.assignee_user_id}</Descriptions.Item>
        <Descriptions.Item label="截止">{task.due_at ? new Date(task.due_at).toLocaleString('zh-CN') : '-'}</Descriptions.Item>
        <Descriptions.Item label="优先级"><TaskPriorityTag priority={task.priority} /></Descriptions.Item>
        <Descriptions.Item label="创建时间">{task.created_at ? new Date(task.created_at).toLocaleString('zh-CN') : '-'}</Descriptions.Item>
        <Descriptions.Item label="退回次数">{task.reopen_count}</Descriptions.Item>
        {task.biz_title && (
          <Descriptions.Item label="业务对象" span={2}>
            {task.biz_url ? <a href={task.biz_url}>{task.biz_title}</a> : task.biz_title}
            <Text type="secondary" style={{ marginLeft: 8 }}>{task.biz_type}:{task.biz_no}</Text>
          </Descriptions.Item>
        )}
      </Descriptions>

      {task.description && (
        <Card size="small" title="任务要求">
          <div style={{ whiteSpace: 'pre-wrap' }}>{task.description}</div>
        </Card>
      )}

      <Card
        size="small"
        title={<Space>自动分析 <TaskAnalysisTag status={task.analysis_status} /></Space>}
        extra={
          (task.can_manage || task.can_act) && task.task_type === 'business'
            ? <Button size="small" onClick={() => doAction(() => agentApi.analyzeTask(task.id), '已加入分析队列')}>重新分析</Button>
            : null
        }
      >
        {task.analysis_status === 'failed' && <Alert type="error" showIcon message={task.analysis_error || '分析失败'} />}
        {task.analysis_result?.summary
          ? <Markdown>{String(task.analysis_result.summary)}</Markdown>
          : <Text type="secondary">{task.analysis_status === 'skipped' ? '通用待办无需自动分析' : '暂无分析结果'}</Text>}
      </Card>

      <Card
        size="small"
        title={`汇报（${task.reports.length} 个版本）`}
        extra={task.can_act ? <Button type="primary" size="small" onClick={() => setReportOpen(true)}>提交汇报</Button> : null}
      >
        {task.reports.length === 0 ? <Empty description="暂无汇报" /> : (
          <Collapse
            items={task.reports.map(report => ({
              key: report.id,
              label: `v${report.version} · ${new Date(report.submitted_at).toLocaleString('zh-CN')}`,
              children: (
                <div>
                  <div style={{ whiteSpace: 'pre-wrap' }}>{report.summary}</div>
                  {report.result_data && (
                    <>
                      <Divider style={{ margin: '8px 0' }} />
                      <Text strong>结果数据</Text>
                      <pre style={{ fontSize: 12, background: '#f8fafc', padding: 8, borderRadius: 6 }}>{JSON.stringify(report.result_data, null, 2)}</pre>
                    </>
                  )}
                  {report.evidence && report.evidence.length > 0 && (
                    <>
                      <Divider style={{ margin: '8px 0' }} />
                      <Text strong>证据</Text>
                      <pre style={{ fontSize: 12, background: '#f8fafc', padding: 8, borderRadius: 6 }}>{JSON.stringify(report.evidence, null, 2)}</pre>
                    </>
                  )}
                </div>
              ),
            }))}
          />
        )}
      </Card>
    </Space>
  )

  const management = (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Alert type="info" showIcon message="主管操作会实时校验层级、范围与任务状态；已完成任务不能直接改派。" />
      <Space wrap>
        <Button onClick={() => doAction(() => agentApi.remindTask(task.id), '已催办')}>催办</Button>
        <Button onClick={() => { updateForm.setFieldsValue({ due_at: task.due_at ? dayjs(task.due_at) : null, priority: task.priority }); setUpdateOpen(true) }}>改期/优先级</Button>
        <Button disabled={task.status === 'completed' || task.status === 'cancelled'} onClick={() => setReassignOpen(true)}>改派</Button>
        <Button danger disabled={task.status === 'completed' || task.status === 'cancelled'} onClick={() => setCancelOpen(true)}>取消</Button>
        <Button disabled={task.status !== 'completed'} onClick={() => setReturnOpen(true)}>退回重做</Button>
        <Button onClick={openAssistant}>和我一起处理</Button>
      </Space>
    </Space>
  )

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space wrap>
            <Title level={4} style={{ margin: 0 }}>{task.title}</Title>
            <TaskStatusTag status={task.status} isOverdue={task.is_overdue} />
            <TaskPriorityTag priority={task.priority} />
          </Space>
          <Text type="secondary">{task.task_no} · 截止 {task.due_at ? new Date(task.due_at).toLocaleString('zh-CN') : '-'}</Text>
          <Space wrap>
            {task.can_act && task.status === 'pending' && <Button type="primary" onClick={() => doAction(() => agentApi.startTask(task.id), '已开始处理')}>开始处理</Button>}
            {task.can_act && (task.status === 'pending' || task.status === 'in_progress') && <Button onClick={() => setBlockOpen(true)}>标记阻塞</Button>}
            {task.can_act && task.status === 'blocked' && <Button type="primary" onClick={() => doAction(() => agentApi.resumeTask(task.id), '已恢复处理')}>恢复处理</Button>}
            {task.can_act && <Button onClick={() => setReportOpen(true)}>提交汇报</Button>}
            {task.can_act && task.task_type === 'business' && <Button onClick={() => doAction(() => agentApi.analyzeTask(task.id), '已加入分析队列')}>重新分析</Button>}
            <Button onClick={openAssistant}>打开任务对话</Button>
            <Button onClick={() => navigate('/agents/tasks')}>返回列表</Button>
          </Space>
        </Space>
      </Card>

      <Card>
        <Tabs
          items={[
            { key: 'overview', label: '概况/汇报', children: overview },
            { key: 'events', label: '动态', children: <TaskTimeline events={task.events} /> },
            {
              key: 'chat', label: '对话',
              children: (
                <Card
                  size="small"
                  title="我的任务会话"
                  extra={<Button size="small" onClick={load}>刷新</Button>}
                >
                  <Text type="secondary">任务会话由当前智能体独立维护，主管与员工互不可见。</Text>
                  <div style={{ margin: '12px 0' }}>
                    <Button type="primary" onClick={openAssistant}>打开任务会话</Button>
                  </div>
                  {taskChat?.messages?.length ? (
                    <List
                      dataSource={taskChat.messages}
                      renderItem={(item: any) => (
                        <List.Item style={{ display: 'block' }}>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {item.role === 'user' ? '我' : '智能体'} · {item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : ''}
                          </Text>
                          {item.role === 'assistant'
                            ? <Markdown>{item.content || ''}</Markdown>
                            : <div style={{ whiteSpace: 'pre-wrap' }}>{item.content}</div>}
                        </List.Item>
                      )}
                    />
                  ) : <Empty description="还没有任务对话" />}
                </Card>
              ),
            },
            ...(task.can_manage ? [{ key: 'manage', label: '管理动作', children: management }] : []),
          ]}
        />
      </Card>

      <ReportEditor open={reportOpen} loading={submitting} onCancel={() => setReportOpen(false)} onSubmit={submitReport} />

      <Modal
        title="标记阻塞" open={blockOpen} onCancel={() => setBlockOpen(false)}
        onOk={async () => { if (!blockReason.trim()) { message.warning('请填写阻塞原因'); return } await doAction(() => agentApi.blockTask(task.id, blockReason), '已标记阻塞并通知主管'); setBlockOpen(false); setBlockReason('') }}
        okText="确认"
      >
        <Input.TextArea rows={4} value={blockReason} onChange={e => setBlockReason(e.target.value)} placeholder="必填：阻塞原因" />
      </Modal>

      <Modal
        title="取消任务" open={cancelOpen} onCancel={() => setCancelOpen(false)}
        onOk={async () => { if (!cancelReason.trim()) { message.warning('请填写取消原因'); return } await doAction(() => agentApi.cancelTask(task.id, cancelReason), '任务已取消'); setCancelOpen(false); setCancelReason('') }}
        okText="确认取消" okButtonProps={{ danger: true }}
      >
        <Input.TextArea rows={4} value={cancelReason} onChange={e => setCancelReason(e.target.value)} placeholder="必填：取消原因" />
      </Modal>

      <Modal
        title="退回重做" open={returnOpen} onCancel={() => setReturnOpen(false)}
        onOk={async () => { await doAction(() => agentApi.returnTask(task.id, returnReason), '任务已退回重做'); setReturnOpen(false); setReturnReason('') }}
        okText="确认退回"
      >
        <Input.TextArea rows={4} value={returnReason} onChange={e => setReturnReason(e.target.value)} placeholder="退回原因（可选）" />
      </Modal>

      <Modal
        title="修改截止/优先级" open={updateOpen} onCancel={() => setUpdateOpen(false)}
        onOk={async () => {
          const values = await updateForm.validateFields()
          await doAction(() => agentApi.patchTask(task.id, {
            due_at: values.due_at ? values.due_at.format('YYYY-MM-DDTHH:mm:ss') : undefined,
            priority: values.priority,
          }), '任务已更新')
          setUpdateOpen(false)
        }}
        okText="保存"
      >
        <Form form={updateForm} layout="vertical">
          <Form.Item name="due_at" label="截止时间"><DatePicker showTime style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="priority" label="优先级">
            <Select options={[
              { value: 'low', label: '低' }, { value: 'normal', label: '普通' },
              { value: 'high', label: '高' }, { value: 'urgent', label: '紧急' },
            ]} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="改派任务" open={reassignOpen} onCancel={() => setReassignOpen(false)}
        onOk={async () => {
          if (!reassignUserId) { message.warning('请选择新接收人'); return }
          await doAction(() => agentApi.reassignTask(task.id, reassignUserId), '任务已改派')
          setReassignOpen(false)
          setReassignUserId(null)
        }}
        okText="确认改派"
      >
        <Select
          style={{ width: '100%' }}
          placeholder="选择直属子智能体"
          value={reassignUserId || undefined}
          onChange={setReassignUserId}
          options={children.filter(c => c.user_id !== task.assignee_user_id).map(c => ({ value: c.user_id, label: c.name || c.username }))}
        />
      </Modal>
    </Space>
  )
}
