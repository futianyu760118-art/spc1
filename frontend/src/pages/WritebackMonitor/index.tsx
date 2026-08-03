import React, { useEffect, useState } from 'react'
import { PageContainer, ProTable } from '@ant-design/pro-components'
import { Button, Space, Tag, message, Card, Row, Col, Statistic } from 'antd'
import { writebackApi } from '@/services/api/writeback'
import { ReloadOutlined, RedoOutlined } from '@ant-design/icons'
import type { ProColumns } from '@ant-design/pro-components'

interface Stats {
  dead: number
  pending: number
  failed: number
  done_24h: number
  success_rate_1h: number
  worker_alive: boolean
}

interface QueueItem {
  id: number
  writeback_type: string
  business_table: string
  business_pk: string
  status: string
  error_message: string | null
  created_at: string
  updated_at: string
  attempt_count: number
}

export default function WritebackMonitor() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(false)
  const [retryingId, setRetryingId] = useState<number | null>(null)

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
        status: 'failed',
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
    } catch {
      message.error('重试失败')
    } finally {
      setRetryingId(null)
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
      dataIndex: 'error_message',
      key: 'error_message',
      ellipsis: true,
      render: (_dom, record) => (
        <span style={{ color: '#ef4444', fontSize: 12 }}>{record.error_message || '-'}</span>
      ),
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (_dom, record) => record.created_at ? new Date(record.created_at).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_dom, record) => (
        <Button
          size="small"
          type="link"
          icon={<RedoOutlined />}
          loading={retryingId === record.id}
          onClick={() => handleRetry(record.id)}
        >
          重试
        </Button>
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
              title={<span style={{ color: stats && stats.dead > 0 ? '#ef4444' : undefined }}>死信</span>}
              value={stats?.dead ?? 0}
              valueStyle={stats && stats.dead > 0 ? { color: '#ef4444' } : undefined}
            />
          </Col>
          <Col span={4}>
            <Statistic title="Pending" value={stats?.pending ?? 0} />
          </Col>
          <Col span={4}>
            <Statistic
              title="Failed"
              value={stats?.failed ?? 0}
              valueStyle={{ color: '#f97316' }}
            />
          </Col>
          <Col span={4}>
            <Statistic title="Done 24h" value={stats?.done_24h ?? 0} valueStyle={{ color: '#3b82f6' }} />
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
              value={stats?.worker_alive ? '运行中' : '已停止'}
              valueStyle={{ color: stats?.worker_alive ? '#22c55e' : '#ef4444' }}
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
          <Button
            key="refresh"
            icon={<ReloadOutlined />}
            onClick={() => fetchStats()}
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
