import { useState } from 'react'
import type { ClipboardEvent } from 'react'
import { useLocation } from 'react-router-dom'
import { Button, Modal, Form, Input, Select, Upload, message, Tooltip, Image } from 'antd'
import type { UploadFile } from 'antd/es/upload/interface'
import { CloseOutlined, MessageOutlined, UploadOutlined } from '@ant-design/icons'
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
      // 错误已由全局拦截器提示
    }
  }

  const handlePasteImage = async (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const items = Array.from(event.clipboardData?.items || [])
    const imageItems = items.filter(item => item.type.startsWith('image/'))
    if (!imageItems.length) return

    event.preventDefault()

    const remaining = 5 - fileList.length
    if (remaining <= 0) {
      message.warning('最多只能上传5个附件')
      return
    }

    const files = imageItems
      .slice(0, remaining)
      .map((item, index) => {
        const file = item.getAsFile()
        if (!file) return null
        const ext = file.type.split('/')[1] || 'png'
        return new File([file], `粘贴图片-${Date.now()}-${index + 1}.${ext}`, { type: file.type })
      })
      .filter(Boolean) as File[]

    if (!files.length) return

    const uploadingFiles: UploadFile[] = files.map((file, index) => ({
      uid: `paste-${Date.now()}-${index}`,
      name: file.name,
      status: 'uploading',
      size: file.size,
      type: file.type,
      originFileObj: file as any,
      thumbUrl: URL.createObjectURL(file),
    }))

    setFileList(prev => [...prev, ...uploadingFiles].slice(0, 5))

    await Promise.all(uploadingFiles.map(async (uploadFile, index) => {
      try {
        const res: any = await fileApi.upload(files[index], 'feedback')
        setFileList(prev => prev.map(f => (
          f.uid === uploadFile.uid ? { ...f, status: 'done', response: res.data, url: res.data?.url } : f
        )))
      } catch (e: any) {
        setFileList(prev => prev.map(f => (
          f.uid === uploadFile.uid ? { ...f, status: 'error' } : f
        )))
        // 错误已由全局拦截器提示
      }
    }))
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      const attachments = fileList
        .filter(f => f.status === 'done')
        .map(f => {
          const r: any = (f as any).response
          return r ? { key: r.key, url: r.url, name: r.name, size: r.size, mime: r.mime } : null
        })
        .filter(Boolean)
      await feedbackApi.create({ ...values, attachments })
      message.success('感谢您的反馈！我们会尽快处理')
      setOpen(false)
    } catch (e: any) {
      if (e?.errorFields) return
      // 错误已由全局拦截器提示
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <Tooltip title="问题反馈">
        <div
          className="tbv2-feedback-btn"
          onClick={openModal}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              openModal()
            }
          }}
        >
          <MessageOutlined />
          <span>反馈</span>
        </div>
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
          <Form.Item
            label="粘贴图片"
            extra="点击输入框后按 Ctrl+V，可直接粘贴截图或复制的图片"
          >
            <Input.TextArea
              rows={2}
              placeholder="点击这里粘贴图片，图片会自动上传到附件列表"
              onPaste={handlePasteImage}
            />
            {fileList.some(file => file.uid.startsWith('paste-')) && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                {fileList
                  .filter(file => file.uid.startsWith('paste-'))
                  .map(file => (
                    <div
                      key={file.uid}
                      style={{
                        position: 'relative',
                        width: 96,
                        height: 96,
                        border: '1px solid #d9d9d9',
                        borderRadius: 8,
                        overflow: 'hidden',
                        background: '#fafafa',
                      }}
                    >
                      <Image
                        src={file.url || file.thumbUrl}
                        alt={file.name}
                        width={96}
                        height={96}
                        style={{ objectFit: 'cover' }}
                      />
                      <Button
                        type="text"
                        size="small"
                        icon={<CloseOutlined />}
                        onClick={() => setFileList(prev => prev.filter(item => item.uid !== file.uid))}
                        style={{
                          position: 'absolute',
                          top: 2,
                          right: 2,
                          width: 22,
                          height: 22,
                          color: '#fff',
                          background: 'rgba(0, 0, 0, 0.45)',
                        }}
                      />
                    </div>
                  ))}
              </div>
            )}
          </Form.Item>
          <Form.Item label="附件" extra="单文件≤10MB，最多5个">
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
