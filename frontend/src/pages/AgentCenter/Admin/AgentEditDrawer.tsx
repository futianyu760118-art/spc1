import React, { useEffect, useState } from 'react'
import {
  Button, Drawer, Form, Input, Radio, Select, Switch, message,
} from 'antd'
import { userApi } from '../../../services/api'
import { agentApi, AgentCapability, AgentSkillBrief } from '../../../services/agent'

interface RoleOption {
  id: number
  role_name: string
}

interface Props {
  open: boolean
  agent: any | null
  onClose: () => void
  onSaved: () => void
}

export default function AgentEditDrawer({ open, agent, onClose, onSaved }: Props) {
  const [form] = Form.useForm()
  const [capabilities, setCapabilities] = useState<AgentCapability[]>([])
  const [skillOptions, setSkillOptions] = useState<AgentSkillBrief[]>([])
  const [roles, setRoles] = useState<RoleOption[]>([])
  const [saving, setSaving] = useState(false)
  const scopeType = Form.useWatch('scope_type', form)

  const loadOptions = async () => {
    const [capRes, skillRes, roleRes]: any = await Promise.all([
      agentApi.capabilities(),
      agentApi.adminSkills({ page_size: 100 }).catch(() => ({ data: { items: [] } })),
      userApi.roles({ page_size: 500 }).catch(() => {
        message.warning('角色列表加载失败，无法按角色开放')
        return { data: { items: [] } }
      }),
    ])
    setCapabilities((capRes.data?.items || []).filter((cap: AgentCapability) => cap.grantable))
    setSkillOptions(skillRes.data?.items || [])
    setRoles(roleRes.data?.items || [])
  }

  useEffect(() => {
    if (!open) return
    form.resetFields()
    form.setFieldsValue({
      name: agent?.name || '',
      capabilities: (agent?.capabilities || []).map((cap: { code: string }) => cap.code),
      skill_ids: (agent?.skills || []).map((skill: AgentSkillBrief) => skill.id),
      scope_type: agent?.scope_type || 'all',
      scope_role_ids: agent?.scope_role_ids || [],
      description: agent?.description || '',
      status: agent?.status ? agent.status === 'active' : true,
    })
    loadOptions()
  }, [open, agent, form])

  const submit = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      const payload = {
        name: values.name.trim(),
        capabilities: values.capabilities || [],
        skill_ids: values.skill_ids || [],
        scope_type: values.scope_type,
        scope_role_ids: values.scope_type === 'roles' ? values.scope_role_ids : null,
        description: values.description || null,
        status: values.status ? 'active' : 'disabled',
      }
      if (agent) {
        await agentApi.updateAgent(agent.id, payload)
        message.success('已保存')
      } else {
        const res: any = await agentApi.createAgent(payload)
        message.success(`已创建（${res.data?.agent_no || '编码自动生成'}）`)
      }
      onSaved()
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <Drawer
      title={agent ? `编辑智能体 · ${agent.name}` : '新建智能体'}
      width={560}
      open={open}
      onClose={onClose}
      destroyOnClose
      className="sc-page"
      footer={(
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" loading={saving} onClick={submit}>保存</Button>
        </div>
      )}
    >
      <Form form={form} layout="vertical">
        <Form.Item label="编码">
          <Input value={agent?.agent_no || ''} disabled placeholder="保存后自动生成（AG-xxxxxx）" />
        </Form.Item>
        <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入智能体名称' }]}>
          <Input maxLength={64} placeholder="全局唯一，如：订单查询员" />
        </Form.Item>
        <Form.Item
          name="capabilities" label="能力"
          extra="可选；技能型智能体可以不选能力，技能不授予数据/写能力"
        >
          <Select
            mode="multiple"
            placeholder="选择该智能体具备的能力（可多选）"
            options={capabilities.map(cap => ({
              value: cap.code,
              label: `${cap.name}（${cap.code}）`,
            }))}
          />
        </Form.Item>
        <Form.Item name="skill_ids" label="技能" extra="最多绑定 10 个；技能只提供方法与上下文，不授予能力">
          <Select
            mode="multiple"
            allowClear
            showSearch
            optionFilterProp="label"
            maxTagCount="responsive"
            placeholder="选择该智能体可用的技能（可多选）"
            options={skillOptions.map(skill => ({
              value: skill.id,
              label: `${skill.name}${skill.status === 'disabled' ? '（停用）' : ''}`,
            }))}
          />
        </Form.Item>
        <Form.Item name="scope_type" label="开放范围" rules={[{ required: true }]}>
          <Radio.Group
            options={[
              { value: 'all', label: '所有人可勾选' },
              { value: 'roles', label: '指定角色' },
            ]}
          />
        </Form.Item>
        {scopeType === 'roles' && (
          <Form.Item
            name="scope_role_ids" label="开放角色"
            rules={[{ required: true, message: '请选择至少一个角色' }]}
          >
            <Select
              mode="multiple"
              placeholder="选择可勾选该智能体的角色"
              options={roles.map(role => ({ value: role.id, label: role.role_name }))}
            />
          </Form.Item>
        )}
        <Form.Item name="description" label="说明">
          <Input.TextArea rows={3} maxLength={500} placeholder="展示给用户，并帮助助手选择合适的成员" />
        </Form.Item>
        <Form.Item name="status" label="启用" valuePropName="checked" style={{ marginBottom: 0 }}>
          <Switch />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
