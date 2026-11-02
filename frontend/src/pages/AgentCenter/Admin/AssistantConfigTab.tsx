import { useCallback, useEffect, useState } from 'react'
import {
  Button, Col, Form, Input, InputNumber, Row, Spin, Switch,
  Table, message,
} from 'antd'
import { agentApi } from '../../../services/agent'

interface ToolItem { name: string; display_name: string; description: string; disabled: boolean }

export default function AssistantConfigTab() {
  const [form] = Form.useForm()
  const [tools, setTools] = useState<ToolItem[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await agentApi.assistantConfig()
      const d = res.data
      form.setFieldsValue(d.config)
      setTools(d.tools)
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setLoading(false)
    }
  }, [form])

  useEffect(() => { refresh() }, [refresh])

  const save = async () => {
    const values = await form.validateFields()
    const disabled = tools.filter((t) => t.disabled).map((t) => t.name)
    setSaving(true)
    try {
      const res: any = await agentApi.saveAssistantConfig({
        config: { ...values, disabled_tools: disabled },
      })
      message.success(`已保存（版本 v${res.data.version}，即时生效）`)
      if (res.data.warning) message.warning(res.data.warning)
      refresh()
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setSaving(false)
    }
  }

  const enabledCount = tools.filter((t) => !t.disabled).length

  return (
    <div className="sc-page">
      <Spin spinning={loading}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 960 }}>
          <div style={{ padding: '10px 14px', background: '#eef0fe', borderRadius: 10, color: '#4c4dc2', fontSize: 13 }}>
            系统提示词支持 <code>{'{{TOOLS}}'}</code> 占位符：构建对话时自动注入当前启用工具清单；两段提示词留空即恢复内置默认。
          </div>

          <div className="sc-card" style={{ padding: '0 16px 16px' }}>
            <div className="sc-card-head" style={{ padding: '14px 0 4px' }}>
              <h3>提示词</h3>
              <span className="sc-hint">留空 = 恢复内置默认</span>
            </div>
            <Form form={form} layout="vertical">
              <Form.Item name="system_prompt" label="系统提示词">
                <Input.TextArea rows={12}/>
              </Form.Item>
              <Form.Item name="intent_prompt" label="意图识别提示词" style={{ marginBottom: 0 }}>
                <Input.TextArea rows={8}/>
              </Form.Item>
            </Form>
          </div>

          <div className="sc-card" style={{ padding: '0 16px 16px' }}>
            <div className="sc-card-head" style={{ padding: '14px 0 4px' }}>
              <h3>模型参数</h3>
              <span className="sc-hint">模型名留空则沿用 .env 默认</span>
            </div>
            <Form form={form} layout="vertical">
              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item name="model_name" label="模型名">
                    <Input allowClear placeholder="如 glm-4.6 / gpt-4o-mini"/>
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name="temperature" label="温度" initialValue={0.1}>
                    <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }}/>
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name="max_tokens" label="最大输出 token" initialValue={4096}>
                    <InputNumber min={256} max={32768} step={256} style={{ width: '100%' }}/>
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name="max_tool_rounds" label="LLM 轮数上限（编排器）" initialValue={6}>
                    <InputNumber min={1} max={20} style={{ width: '100%' }}/>
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name="max_agent_calls" label="智能体调用次数上限" initialValue={8} style={{ marginBottom: 0 }}>
                    <InputNumber min={1} max={50} style={{ width: '100%' }}/>
                  </Form.Item>
                </Col>
              </Row>
            </Form>
          </div>

          <div className="sc-card" style={{ padding: '0 0 4px' }}>
            <div className="sc-card-head" style={{ padding: '12px 16px' }}>
              <h3>工具启停</h3>
              <span className="sc-hint sc-mono">{enabledCount}/{tools.length} 启用</span>
            </div>
            <Table rowKey="name" size="small" pagination={false}
                   dataSource={tools}
                   columns={[
                     { title: '工具', dataIndex: 'display_name', width: 220 },
                     { title: '说明', dataIndex: 'description', ellipsis: true },
                     {
                       title: '启用', dataIndex: 'disabled', width: 90,
                       render: (v: boolean, row: ToolItem) => (
                         <Switch checked={!v} onChange={(checked) => {
                           setTools((prev) => prev.map((t) =>
                             t.name === row.name ? { ...t, disabled: !checked } : t))
                         }}/>
                       ),
                     },
                   ]}/>
          </div>

          <div>
            <Button type="primary" loading={saving} onClick={save}>保存配置</Button>
          </div>
        </div>
      </Spin>
    </div>
  )
}
