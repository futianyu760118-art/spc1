import React, { useCallback, useEffect, useState } from 'react'
import { Alert, Form, Modal, Radio, Select, Space, Typography, message } from 'antd'
import { agentApi, AgentInfo, AgentUserOption } from '../../../services/agent'

const { Text } = Typography

interface Props {
  open: boolean
  onClose: () => void
  onSuccess?: () => void
  preselectedAgentIds?: number[]
}

export default function BindUsersModal({
  open, onClose, onSuccess, preselectedAgentIds = [],
}: Props) {
  const [form] = Form.useForm()
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [users, setUsers] = useState<AgentUserOption[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const selectedAgents = Form.useWatch('agent_ids', form) || []
  const selectedUsers = Form.useWatch('user_ids', form) || []
  const preselectKey = preselectedAgentIds.join(',')

  const loadOptions = useCallback(async () => {
    setLoading(true)
    try {
      const [agentRes, userRes]: any = await Promise.all([
        agentApi.adminAgents({ page_size: 100 }),
        agentApi.adminUsers({ limit: 500 }),
      ])
      setAgents(agentRes.data?.items || [])
      setUsers(userRes.data?.items || [])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!open) return
    form.resetFields()
    form.setFieldsValue({
      action: 'bind',
      agent_ids: preselectedAgentIds,
      user_ids: [],
    })
    loadOptions()
  }, [open, preselectKey, form, loadOptions])

  const submit = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      const res: any = await agentApi.bindAgentUsers({
        agent_ids: values.agent_ids,
        user_ids: values.user_ids,
        action: values.action,
      })
      const data = res.data || {}
      if (values.action === 'bind') {
        message.success(`已绑定 ${data.created || 0} 个关系`)
      } else {
        message.success(`已解绑 ${data.removed || 0} 个关系`)
      }
      if (data.skipped) {
        message.warning(`跳过 ${data.skipped} 个关系`)
      }
      const details = [
        ...(data.errors || []),
        ...((data.skipped_details || []).map(
          (item: any) => `智能体 #${item.agent_id} × 用户 #${item.user_id}：${item.reason}`,
        )),
      ]
      if (details.length) {
        Modal.warning({
          title: '部分关系未处理',
          width: 620,
          content: (
            <div style={{ maxHeight: 280, overflow: 'auto' }}>
              {details.slice(0, 50).map((item: string, index: number) => (
                <div key={index}>{item}</div>
              ))}
            </div>
          ),
        })
      }
      onSuccess?.()
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title="批量绑定 / 解绑用户"
      open={open}
      onCancel={onClose}
      onOk={submit}
      confirmLoading={saving}
      okText="执行"
      width={640}
      destroyOnClose
    >
      <Form form={form} layout="vertical">
        <Form.Item name="action" label="操作" rules={[{ required: true }]}>
          <Radio.Group
            options={[
              { value: 'bind', label: '绑定' },
              { value: 'unbind', label: '解绑' },
            ]}
          />
        </Form.Item>
        <Form.Item
          name="agent_ids" label="智能体"
          rules={[{ required: true, message: '请选择至少一个智能体' }]}
        >
          <Select
            mode="multiple"
            allowClear
            showSearch
            optionFilterProp="label"
            maxTagCount="responsive"
            loading={loading}
            placeholder="可多选智能体"
            options={agents.map(agent => ({
              value: agent.id,
              label: `${agent.name}（${agent.agent_no}）${agent.status === 'disabled' ? '（停用）' : ''}`,
            }))}
          />
        </Form.Item>
        <Form.Item
          name="user_ids" label="用户"
          rules={[{ required: true, message: '请选择至少一个用户' }]}
        >
          <Select
            mode="multiple"
            allowClear
            showSearch
            optionFilterProp="label"
            maxTagCount="responsive"
            loading={loading}
            placeholder="可多选用户（按姓名/登录名搜索）"
            options={users.map(user => ({
              value: user.id,
              label: `${user.display_name}（${user.username}${user.role_name ? ` / ${user.role_name}` : ''}）`,
            }))}
          />
        </Form.Item>
        <Space direction="vertical" size={4}>
          <Text type="secondary" className="ac-fs-xs">
            本次将处理 {selectedAgents.length} 个智能体 × {selectedUsers.length} 个用户
            = {selectedAgents.length * selectedUsers.length} 个关系（单次上限 10000）。
          </Text>
          <Alert
            type="info"
            showIcon
            message="绑定会校验智能体的开放范围与启停状态；解绑不受开放范围限制。"
          />
        </Space>
      </Form>
    </Modal>
  )
}
