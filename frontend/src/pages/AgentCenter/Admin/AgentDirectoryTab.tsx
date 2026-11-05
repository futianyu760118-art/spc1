import React, { useCallback, useEffect, useState } from 'react'
import { Button, Empty, Input, Pagination, Select, Spin } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { agentApi, AgentInfo } from '../../../services/agent'
import AgentCard from './AgentCard'
import AgentEditDrawer from './AgentEditDrawer'

const PAGE_SIZE = 9

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'active', label: '启用' },
  { value: 'disabled', label: '停用' },
]

interface Props {
  canManage: boolean
  createSignal: number
  onCreateConsumed: () => void
  onBindUsers: (agentIds: number[]) => void
  onChanged: () => void
}

export default function AgentDirectoryTab({
  canManage, createSignal, onCreateConsumed, onBindUsers, onChanged,
}: Props) {
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [editingAgent, setEditingAgent] = useState<AgentInfo | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await agentApi.adminAgents({
        keyword, status, page, page_size: PAGE_SIZE,
      })
      setAgents(res.data?.items || [])
      setTotal(Number(res.data?.total || 0))
    } finally {
      setLoading(false)
    }
  }, [keyword, status, page])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (createSignal > 0) {
      setEditingAgent(null)
      setEditOpen(true)
      onCreateConsumed()
    }
  }, [createSignal, onCreateConsumed])

  const openEdit = (agent: AgentInfo) => {
    setEditingAgent(agent)
    setEditOpen(true)
  }

  const openCreate = () => {
    setEditingAgent(null)
    setEditOpen(true)
  }

  return (
    <div className="ai-card">
      <div className="ai-toolbar">
        <Input.Search
          placeholder="搜索名称 / 编号"
          allowClear
          style={{ width: 260 }}
          onSearch={value => { setKeyword(value); setPage(1) }}
        />
        <Select
          value={status}
          style={{ width: 130 }}
          options={STATUS_OPTIONS}
          onChange={value => { setStatus(value); setPage(1) }}
        />
        <span className="ai-toolbar-meta">共 {total} 个</span>
      </div>

      <Spin spinning={loading}>
        {agents.length === 0 && !loading ? (
          <div className="ai-empty">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的智能体">
              {canManage && !keyword && !status && (
                <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                  新建第一个智能体
                </Button>
              )}
            </Empty>
          </div>
        ) : (
          <div className="ai-agent-grid">
            {agents.map(agent => (
              <AgentCard key={agent.id} agent={agent} onEdit={openEdit} />
            ))}
          </div>
        )}
      </Spin>

      {total > PAGE_SIZE && (
        <div className="ai-pagination">
          <Pagination
            size="small"
            current={page}
            pageSize={PAGE_SIZE}
            total={total}
            showSizeChanger={false}
            onChange={setPage}
          />
        </div>
      )}

      <AgentEditDrawer
        open={editOpen}
        agent={editingAgent}
        onClose={() => setEditOpen(false)}
        onSaved={() => { load(); onChanged() }}
        onBindUsers={agentId => onBindUsers([agentId])}
      />
    </div>
  )
}
