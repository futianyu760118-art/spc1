import React, { useCallback, useEffect, useState } from 'react'
import { Button, Drawer, Empty, Input, List, Space, message } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { agentApi, AgentCapabilityItem } from '../../../services/agent'
import { CapabilityTags } from '../../../components/Agent/CapabilityTags'

interface Candidate {
  id: number
  agent_no: string
  name: string
  capabilities: AgentCapabilityItem[]
  description?: string | null
}

interface Props {
  open: boolean
  existingIds: number[]
  onClose: () => void
  onAdded: () => void
}

export default function AddMemberDrawer({ open, existingIds, onClose, onAdded }: Props) {
  const [keyword, setKeyword] = useState('')
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [loading, setLoading] = useState(false)
  const [addingId, setAddingId] = useState<number | null>(null)

  const load = useCallback(async (value: string) => {
    setLoading(true)
    try {
      const res: any = await agentApi.candidates(value)
      setCandidates(res.data?.items || [])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!open) return
    setKeyword('')
    load('')
  }, [open, load])

  const addMember = async (agentId: number) => {
    setAddingId(agentId)
    try {
      await agentApi.addMember(agentId)
      message.success('已加入团队')
      onAdded()
      await load(keyword)
    } finally {
      setAddingId(null)
    }
  }

  const visible = candidates.filter(item => !existingIds.includes(item.id))

  return (
    <Drawer
      title="添加团队成员"
      width={520}
      open={open}
      onClose={onClose}
      destroyOnClose
      className="sc-page"
    >
      <Space direction="vertical" style={{ width: '100%' }} size={12}>
        <Input.Search
          placeholder="搜索名称 / 编号"
          allowClear
          value={keyword}
          onChange={event => setKeyword(event.target.value)}
          onSearch={value => load(value)}
        />
        <List
          loading={loading}
          dataSource={visible}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有可添加的智能体" /> }}
          renderItem={(item: Candidate) => (
            <List.Item
              actions={[
                <Button
                  key="add"
                  type="link"
                  size="small"
                  icon={<PlusOutlined />}
                  loading={addingId === item.id}
                  onClick={() => addMember(item.id)}
                >
                  加入
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={(
                  <Space size={6}>
                    <span>{item.name}</span>
                    <span className="ai-muted">{item.agent_no}</span>
                  </Space>
                )}
                description={(
                  <Space direction="vertical" size={4}>
                    <CapabilityTags items={item.capabilities} max={3} />
                    {item.description && <span className="ai-muted">{item.description}</span>}
                  </Space>
                )}
              />
            </List.Item>
          )}
        />
      </Space>
    </Drawer>
  )
}
