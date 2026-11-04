import React, { useCallback, useEffect, useState } from 'react'
import {
  Button, Empty, Input, Pagination, Select, Spin,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { agentApi, AgentInfo } from '../../../services/agent'
import AgentEditDrawer from './AgentEditDrawer'
import AgentCard from './AgentCard'

const PAGE_SIZE = 6

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'active', label: '启用' },
  { value: 'disabled', label: '停用' },
]

interface Props {
  createSignal: number
  onCreateConsumed: () => void
  onBindUsers: (agentIds: number[]) => void
}

export default function AgentDirectoryTab({ createSignal, onCreateConsumed, onBindUsers }: Props) {
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
      setTotal(res.data?.total || 0)
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

  return (
    <div className="ai-card">
      <div className="ai-toolbar">
        <Input.Search
          placeholder="搜索名称 / 编号"
          allowClear
          style={{ width: 280 }}
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
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有智能体">
              <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditingAgent(null); setEditOpen(true) }}>
                新建第一个智能体
              </Button>
            </Empty>
          </div>
        ) : (
          <div className="ai-agent-grid" style={{ padding: 16 }}>
            {agents.map(agent => (
              <AgentCard
                key={agent.id}
                agent={agent}
                onEdit={openEdit}
                onBindUsers={item => onBindUsers([item.id])}
              />
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
        onSaved={load}
      />
    </div>
  )
}
