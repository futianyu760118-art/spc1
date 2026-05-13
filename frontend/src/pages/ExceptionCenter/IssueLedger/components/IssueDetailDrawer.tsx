import { Modal, Form, Input, Select, DatePicker } from 'antd'
import dayjs from 'dayjs'

interface IssueDetailDrawerProps {
  open: boolean
  issue: any
  onOk: () => void
  onCancel: () => void
  form: any
}

export default function IssueDetailDrawer({ open, issue, onOk, onCancel, form }: IssueDetailDrawerProps) {
  return (
    <Modal
      title={`处置异常 — ${issue?.issue_no}`}
      open={open}
      onOk={onOk}
      onCancel={onCancel}
    >
      <Form form={form} layout="vertical">
        <Form.Item name="owner" label="责任人">
          <Input />
        </Form.Item>
        <Form.Item name="action_taken" label="处理动作">
          <Input.TextArea rows={3} />
        </Form.Item>
        <Form.Item name="commit_date" label="承诺解决日期">
          <DatePicker className="w-full" />
        </Form.Item>
        <Form.Item name="status" label="状态">
          <Select options={[
            { value: 'open', label: '待处理' },
            { value: 'in_progress', label: '处理中' },
            { value: 'closed', label: '已关闭' },
          ]} />
        </Form.Item>
      </Form>
    </Modal>
  )
}
