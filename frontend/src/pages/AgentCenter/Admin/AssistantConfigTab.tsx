import { useCallback, useEffect, useState } from 'react'
import { Button, Form, Input, InputNumber, Spin, message } from 'antd'
import { agentApi } from '../../../services/agent'

export default function AssistantConfigTab() {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await agentApi.assistantConfig()
      form.setFieldsValue(res.data?.config)
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setLoading(false)
    }
  }, [form])

  useEffect(() => { refresh() }, [refresh])

  const save = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      const res: any = await agentApi.saveAssistantConfig({ config: values })
      message.success(`已保存（版本 v${res.data.version}，即时生效）`)
      refresh()
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Spin spinning={loading}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, maxWidth: 980 }}>
        <section className="ac-surface">
          <div className="ac-surface-head">
            <h2>提示词</h2>
            <span className="ac-hint">留空 = 恢复内置默认</span>
          </div>
          <div className="ac-audit-body" style={{ maxWidth: 'none' }}>
            <div className="ac-audit-note" style={{ marginBottom: 12 }}>
              <div>
                系统提示词支持 <code style={{ fontFamily: 'var(--ac-font-mono)' }}>{'{{TOOLS}}'}</code> 占位符：
                构建对话时自动注入已注册工具清单；两段提示词留空即恢复内置默认。
                实际可用性由智能体的能力与技能配置决定。
              </div>
            </div>
            <Form form={form} layout="vertical">
              <Form.Item name="system_prompt" label="系统提示词">
                <Input.TextArea rows={10} style={{ fontFamily: 'var(--ac-font-mono)', fontSize: 11.5 }} />
              </Form.Item>
              <Form.Item name="intent_prompt" label="意图识别提示词" style={{ marginBottom: 0 }}>
                <Input.TextArea rows={6} style={{ fontFamily: 'var(--ac-font-mono)', fontSize: 11.5 }} />
              </Form.Item>
            </Form>
          </div>
        </section>

        <section className="ac-surface">
          <div className="ac-surface-head">
            <h2>模型参数</h2>
            <span className="ac-hint">模型名留空则沿用 .env 默认</span>
          </div>
          <div className="ac-audit-body" style={{ maxWidth: 'none' }}>
            <Form form={form} layout="vertical">
              <div className="ac-form-grid">
                <Form.Item name="model_name" label="模型名">
                  <Input allowClear placeholder="如 gpt-4o-mini / glm-4.6" />
                </Form.Item>
                <Form.Item name="temperature" label="温度" initialValue={0.1}>
                  <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="max_tokens" label="最大输出 token" initialValue={4096}>
                  <InputNumber min={256} max={32768} step={256} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="max_tool_rounds" label="LLM 轮数上限（编排器）" initialValue={6}>
                  <InputNumber min={1} max={20} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="max_agent_calls" label="智能体调用次数上限" initialValue={8} style={{ marginBottom: 0 }}>
                  <InputNumber min={1} max={50} style={{ width: '100%' }} />
                </Form.Item>
              </div>
            </Form>
            <div className="ac-form-actions">
              <Button type="primary" loading={saving} onClick={save}>保存配置</Button>
              <span className="hint">保存后即时生效 · 当前版本 v7</span>
            </div>
          </div>
        </section>
      </div>
    </Spin>
  )
}
