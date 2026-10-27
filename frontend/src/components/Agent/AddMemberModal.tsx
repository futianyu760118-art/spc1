import React, { useCallback, useEffect, useState } from 'react'
import { Input, Modal, Space, Table, Tag, message } from 'antd'
import { agentApi } from '../../services/agent'

interface Candidate {
  id: number
  username: string
  display_name?: string
  employee_name?: string
  role_code?: string
  status: string
  agent_id?: number | null
  bindable: boolean
}

interface Props {
  open: boolean
  onClose: () => void
  onAdded: () => void
}

export const AddMemberModal: React.FC<Props> = ({ open, onClose, onAdded }) => {
  const [keyword, setKeyword] = useState('')
  const [rows, setRows] = useState<Candidate[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async (value: string) => {
    setLoading(true)
    try {
      const res: any = await agentApi.candidates(value)
      setRows(res.data?.items || [])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) {
      setSelected(null)
      load('')
    }
  }, [open, load])

  const handleAdd = async () => {
    if (!selected) {
      message.warning('请选择一个用户')
      return
    }
    setSaving(true)
    try {
      await agentApi.addMember({ user_id: selected })
      message.success('已添加并通知对方，立即生效')
      onAdded()
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title="添加直属成员"
      open={open}
      onCancel={onClose}
      onOk={handleAdd}
      confirmLoading={saving}
      okText="立即绑定"
      width={720}
      destroyOnClose
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <Input.Search
          placeholder="搜索用户名 / 显示名 / 员工姓名"
          allowClear
          onSearch={value => load(value)}
          onChange={e => setKeyword(e.target.value)}
          value={keyword}
        />
        <Table
          size="small"
          rowKey="id"
          loading={loading}
          dataSource={rows}
          pagination={false}
          scroll={{ y: 360 }}
          rowSelection={{
            type: 'radio',
            selectedRowKeys: selected ? [selected] : [],
            onChange: keys => setSelected(Number(keys[0])),
            getCheckboxProps: record => ({ disabled: !record.bindable }),
          }}
          onRow={record => ({
            onClick: () => record.bindable && setSelected(record.id),
            style: { cursor: record.bindable ? 'pointer' : 'not-allowed' },
          })}
          columns={[
            { title: '用户名', dataIndex: 'username', width: 140 },
            { title: '显示名', dataIndex: 'display_name', width: 140 },
            { title: '员工姓名', dataIndex: 'employee_name', width: 120 },
            {
              title: '状态', dataIndex: 'bindable', width: 120,
              render: (bindable: boolean) => bindable
                ? <Tag color="green">可绑定</Tag>
                : <Tag color="default">已有上级/子成员</Tag>,
            },
          ]}
        />
      </Space>
    </Modal>
  )
}
