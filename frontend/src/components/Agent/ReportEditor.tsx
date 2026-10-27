import React, { useEffect } from 'react'
import { Form, Input, message, Modal } from 'antd'

interface Props {
  open: boolean
  loading?: boolean
  onCancel: () => void
  onSubmit: (data: { summary: string; result_data?: Record<string, any>; evidence?: any[] }) => void
}

const { TextArea } = Input

function parseJson(text: string | undefined, label: string): any {
  if (!text || !text.trim()) return undefined
  try {
    return JSON.parse(text)
  } catch {
    throw new Error(`${label} 不是合法 JSON`)
  }
}

export const ReportEditor: React.FC<Props> = ({ open, loading, onCancel, onSubmit }) => {
  const [form] = Form.useForm()

  useEffect(() => {
    if (open) form.resetFields()
  }, [open, form])

  const handleOk = async () => {
    const values = await form.validateFields()
    try {
      const resultData = parseJson(values.result_data, '结果数据')
      const evidence = parseJson(values.evidence, '证据')
      onSubmit({
        summary: values.summary,
        result_data: resultData,
        evidence: evidence,
      })
    } catch (e: any) {
      message.error(e.message || 'JSON 格式错误')
    }
  }

  return (
    <Modal
      title="提交任务汇报"
      open={open}
      onCancel={onCancel}
      onOk={handleOk}
      confirmLoading={loading}
      okText="提交并完成任务"
      width={640}
      destroyOnClose
    >
      <Form form={form} layout="vertical">
        <Form.Item name="summary" label="汇报摘要" rules={[{ required: true, message: '请填写汇报摘要' }]}>
          <TextArea rows={4} placeholder="说明处理结果、结论与需要主管知道的信息" />
        </Form.Item>
        <Form.Item name="result_data" label="结构化结果（JSON，可选）">
          <TextArea rows={4} placeholder='例如 {"conclusion":"可按时交付","risk":"低"}' />
        </Form.Item>
        <Form.Item name="evidence" label="证据列表（JSON 数组，可选）">
          <TextArea rows={4} placeholder='例如 [{"ref":"control-platform://order/xxx","summary":"交期已确认"}]' />
        </Form.Item>
      </Form>
    </Modal>
  )
}
