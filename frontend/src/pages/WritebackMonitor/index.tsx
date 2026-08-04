import React, { useEffect, useState } from 'react'
import { PageContainer, ProTable } from '@ant-design/pro-components'
import { Button, Space, Tag, message, Card, Row, Col, Statistic, Select } from 'antd'
import { writebackApi } from '@/services/api/writeback'
import { ReloadOutlined, RedoOutlined } from '@ant-design/icons'
import type { ProColumns } from '@ant-design/pro-components'

interface Stats {
  queue_depth: {
    dead: number
    pending: number
    failed: number
    done_24h: number
  }
  success_rate_1h: number | null
  avg_duration_ms_1h: number
  by_type: any[]
  recent_failures: any[]
  worker: {
    running: boolean
    last_poll_at: string | null
  }
}

interface QueueItem {
  id: number
  writeback_type: string
  business_table: string
  business_pk: string
  status: string
  last_error: string | null
  retry_count: number
  enqueued_at: string
  picked_at: string | null
  finished_at: string | null
}

export default function WritebackMonitor() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(false)
  const [retryingId, setRetryingId] = useState<number | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('failed')

  const fetchStats = async () => {
    try {
      const res: any = await writebackApi.getStats()
      setStats(res.data || null)
    } catch {
      /* ignore */
    }
  }

  const fetchData = async (params?: any) => {
    setLoading(true)
    try {
      const query: Record<string, any> = {
        page: params?.current || 1,
        page_size: params?.pageSize || 20,
        status: statusFilter,
        ...params,
      }
      const res: any = await writebackApi.listQueue(query)
      return {
        data: res.data?.items || res.data || [],
        total: res.data?.total || 0,
        success: true,
      }
    } catch {
      return { data: [], total: 0, success: false }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStats()
    const timer = setInterval(fetchStats, 10000)
    return () => clearInterval(timer)
  }, [])

  const handleRetry = async (id: number) => {
    setRetryingId(id)
    try {
      await writebackApi.retryQueue(id)
      message.success('已重入队')
      fetchStats()
      fetchData()
    } catch {
      message.error('重试失败')
    } finally {
      setRetryingId(null)
    }
  }

  const handleAbandon = async (id: number) => {
    try {
      await writebackApi.abandonQueue(id)
      message.success('已放弃')
      fetchStats()
      fetchData()
    } catch {
      message.error('操作失败')
    }
  }

  const columns: ProColumns<QueueItem>[] = [
    {
      title: 'Queue ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: '类型',
      dataIndex: 'writeback_type',
      key: 'writeback_type',
      width: 120,
      render: (_dom, record) => <Tag color="blue">{record.writeback_type}</Tag>,
    },
    {
      title: '错误信息',
      dataIndex: 'last_error',
      key: 'last_error',
      ellipsis: true,
      render: (_dom, record) => (
        <span style={{ color: '#ef4444', fontSize: 12 }}>{record.last_error || '-'}</span>
      ),
    },
    {
      title: '重试次数',
      dataIndex: 'retry_count',
      key: 'retry_count',
      width: 80,
    },
    {
      title: '入队时间',
      dataIndex: 'enqueued_at',
      key: 'enqueued_at',
      width: 160,
      render: (_dom, record) => record.enqueued_at ? new Date(record.enqueued_at).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      render: (_dom, record) => (
        <Space size="small">
          <Button
            size="small"
            type="link"
            icon={<RedoOutlined />}
            loading={retryingId === record.id}
            onClick={() => handleRetry(record.id)}
          >
            重试
          </Button>
          {record.status === 'dead' && (
            <Button
              size="small"
              type="link"
              danger
              onClick={() => handleAbandon(record.id)}
            >
              放弃
            </Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <PageContainer
      header={{ title: '回写监控', subTitle: '自动刷新 (10s)' }}
    >
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={24}>
          <Col span={4}>
            <Statistic
              title={<span style={{ color: stats?.queue_depth?.dead ? '#ef4444' : undefined }}>死信</span>}
              value={stats?.queue_depth?.dead ?? 0}
              valueStyle={stats?.queue_depth?.dead ? { color: '#ef4444' } : undefined}
            />
          </Col>
          <Col span={4}>
            <Statistic title="待处理" value={stats?.queue_depth?.pending ?? 0} />
          </Col>
          <Col span={4}>
            <Statistic
              title="失败"
              value={stats?.queue_depth?.failed ?? 0}
              valueStyle={{ color: '#f97316' }}
            />
          </Col>
          <Col span={4}>
            <Statistic title="24h 已完成" value={stats?.queue_depth?.done_24h ?? 0} valueStyle={{ color: '#3b82f6' }} />
          </Col>
          <Col span={4}>
            <Statistic
              title="1h 成功率"
              value={stats?.success_rate_1h != null ? `${(stats.success_rate_1h * 100).toFixed(1)}%` : '-'}
            />
          </Col>
          <Col span={4}>
            <Statistic
              title="Worker"
              value={stats?.worker?.running ? '运行中' : '已停止'}
              valueStyle={{ color: stats?.worker?.running ? '#22c55e' : '#ef4444' }}
            />
          </Col>
        </Row>
      </Card>

      <ProTable<QueueItem>
        headerTitle="失败队列"
        rowKey="id"
        columns={columns}
        request={fetchData}
        loading={loading}
        search={false}
        toolBarRender={() => [
          <Select
            key="status"
            value={statusFilter}
            onChange={(v) => { setStatusFilter(v); fetchData() }}
            style={{ width: 120 }}
            options={[
              { value: 'failed', label: '失败' },
              { value: 'dead', label: '死信' },
              { value: 'pending', label: '待处理' },
              { value: 'processing', label: '处理中' },
            ]}
          />,
          <Button
            key="refresh"
            icon={<ReloadOutlined />}
            onClick={() => { fetchStats(); fetchData() }}
          >
            刷新
          </Button>,
        ]}
        pagination={{ defaultPageSize: 20, showSizeChanger: true }}
        size="small"
      />
    </PageContainer>
  )
}
