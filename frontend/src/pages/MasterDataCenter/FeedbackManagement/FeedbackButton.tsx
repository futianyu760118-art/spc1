import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Button, Modal, Form, Input, Select, Upload, message, Tooltip } from 'antd'
import type { UploadFile } from 'antd/es/upload/interface'
import { MessageOutlined, UploadOutlined } from '@ant-design/icons'
import { feedbackApi, fileApi } from '../../../services/api'

const typeOptions = [
  { label: '问题', value: 'issue' },
  { label: '建议', value: 'suggestion' },
  { label: '咨询', value: 'inquiry' },
]
const severityOptions = [
  { label: '低', value: 'low' },
  { label: '中', value: 'medium' },
  { label: '高', value: 'high' },
]

export default function FeedbackButton() {
  const location = useLocation()
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)
  const [fileList, setFileList] = useState<UploadFile[]>([])

  const openModal = () => {
    form.resetFields()
    setFileList([])
    form.setFieldsValue({ type: 'issue', severity: 'low', page_path: location.pathname })
    setOpen(true)
  }

  const handleUpload = async ({ file, onSuccess, onError }: any) => {
    try {
      const res: any = await fileApi.upload(file, 'feedback')
      onSuccess?.(res.data)
    } catch (e: any) {
      onError?.(e)
      message.error(e?.response?.data?.detail || '上传失败')
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      const attachments = fileList
        .filter(f => f.status === 'done')
        .map(f => {
          const r: any = (f as any).response
          return r ? { key: r.key, url: r.url, name: r.name, size: r.size, mime: r.mime } : null
        })
        .filter(Boolean)
      setSubmitting(true)
      await feedbackApi.create({ ...values, attachments })
      message.success('感谢您的反馈！我们会尽快处理')
      setOpen(false)
    } catch (e: any) {
      if (e?.errorFields) return
      message.error(e?.response?.data?.detail || '提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <Tooltip title="问题反馈">
        <Button
          type="primary"
          icon={<MessageOutlined />}
          onClick={openModal}
          style={{
            height: 36,
            borderRadius: 10,
            background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
            border: 'none',
            fontWeight: 600,
            boxShadow: '0 4px 12px rgba(99, 102, 241, 0.35)',
            paddingInline: 14,
          }}
        >
          问题反馈
        </Button>
      </Tooltip>
      <Modal
        title="提交问题反馈"
        open={open}
        onOk={handleSubmit}
        confirmLoading={submitting}
        onCancel={() => setOpen(false)}
        okText="提交"
        width={600}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="type" label="类型" rules={[{ required: true }]}>
            <Select options={typeOptions} />
          </Form.Item>
          <Form.Item name="severity" label="严重程度" rules={[{ required: true }]}>
            <Select options={severityOptions} />
          </Form.Item>
          <Form.Item name="page_path" label="所在页面">
            <Input placeholder="自动捕获，可手动编辑" />
          </Form.Item>
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请填写标题' }, { max: 100 }]}>
            <Input placeholder="简要描述问题或建议" maxLength={100} showCount />
          </Form.Item>
          <Form.Item name="description" label="详细描述" rules={[{ required: true, message: '请填写描述' }]}>
            <Input.TextArea
              rows={5}
              placeholder="请详细描述问题/建议，包括复现步骤、期望结果等"
              maxLength={2000}
              showCount
            />
          </Form.Item>
          <Form.Item label="附件（可选）" extra="单文件≤10MB，最多5个">
            <Upload
              customRequest={handleUpload}
              fileList={fileList}
              onChange={({ fileList }) => setFileList(fileList.slice(0, 5))}
              maxCount={5}
              multiple
            >
              <Button icon={<UploadOutlined />}>选择文件</Button>
            </Upload>
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}
