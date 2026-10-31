import React, { useEffect, useRef, useState } from 'react'
import { PageContainer, ProTable, type ActionType } from '@ant-design/pro-components'
import {
  Button, Space, Tag, message, Card, Row, Col, Statistic, Select,
  Drawer, Descriptions, Typography, Tooltip, Empty,
} from 'antd'
import { writebackApi } from '@/services/api/writeback'
import { ReloadOutlined, RedoOutlined, EyeOutlined } from '@ant-design/icons'
import type { ProColumns } from '@ant-design/pro-components'

const { Paragraph, Text } = Typography

interface Stats {
  queue_depth: {
    dead: number
    pending: number
    failed: number
    done_24h: number
    [k: string]: number
  }
  success_rate_1h: number | null
  avg_duration_ms_1h: number
  by_type: Array<{ writeback_type: string; pending: number; failed: number; dead: number }>
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
  target_keys: Record<string, any>
  payload: Record<string, any>
  status: string
  retry_count: number
  next_retry_at: string | null
  last_error: string | null
  enqueued_by: string
  enqueued_by_user: string | null
  enqueued_at: string
  picked_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

const STATUS_META: Record<string, { color: string; label: string }> = {
  pending: { color: 'blue', label: '待处理' },
  processing: { color: 'gold', label: '处理中' },
  failed: { color: 'orange', label: '失败' },
  done: { color: 'green', label: '完成' },
  dead: { color: 'red', label: '死信' },
  abandoned: { color: 'default', label: '已放弃' },
}

function fmtTime(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleString('zh-CN') : '-'
}

function renderTargetKeys(targetKeys: Record<string, any> | string | undefined): string {
  if (!targetKeys) return '-'
  let obj: Record<string, any> = targetKeys as any
  if (typeof targetKeys === 'string') {
    try { obj = JSON.parse(targetKeys) } catch { return String(targetKeys) }
  }
  const pairs = Object.entries(obj).map(([k, v]) => `${k}=${v}`)
  return pairs.length ? pairs.join('  ') : '-'
}

export default function WritebackMonitor() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(false)
  const [retryingId, setRetryingId] = useState<number | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [detail, setDetail] = useState<QueueItem | null>(null)
  const actionRef = useRef<ActionType>()

  const fetchStats = async () => {
    try {
      const res: any = await writebackApi.getStats()
      setStats(res || null)
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
        status: params?.status,
        ...params,
      }
      delete query.current
      delete query.pageSize
      if (!query.status) delete query.status
      const res: any = await writebackApi.listQueue(query)
      return {
        data: res?.items || [],
        total: res?.total || 0,
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
      actionRef.current?.reload()
    } catch {
      // 错误已由全局拦截器提示
    } finally {
      setRetryingId(null)
    }
  }

  const handleAbandon = async (id: number) => {
    try {
      await writebackApi.abandonQueue(id)
      message.success('已放弃')
      fetchStats()
      actionRef.current?.reload()
    } catch {
      // 错误已由全局拦截器提示
    }
  }

  const columns: ProColumns<QueueItem>[] = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 70,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 85,
      render: (_dom, record) => {
        const meta = STATUS_META[record.status] || { color: 'default', label: record.status }
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: '类型',
      dataIndex: 'writeback_type',
      key: 'writeback_type',
      width: 110,
      render: (_dom, record) => <Tag color="blue">{record.writeback_type}</Tag>,
    },
    {
      title: '业务对象',
      key: 'business',
      width: 170,
      render: (_dom, record) => (
        <Tooltip title={`${record.business_table} #${record.business_pk}`}>
          <span style={{ fontSize: 12 }}>
            <code>{record.business_table}</code>
            <span style={{ color: '#94a3b8' }}> #</span>
            {record.business_pk}
          </span>
        </Tooltip>
      ),
    },
    {
      title: '目标键',
      key: 'target_keys',
      width: 200,
      ellipsis: true,
      render: (_dom, record) => {
        const txt = renderTargetKeys(record.target_keys)
        return (
          <Tooltip title={txt}>
            <span style={{ fontSize: 12 }}>{txt}</span>
          </Tooltip>
        )
      },
    },
    {
      title: '错误信息',
      dataIndex: 'last_error',
      key: 'last_error',
      ellipsis: true,
      render: (_dom, record) => (
        <Tooltip title={record.last_error || undefined}>
          <span style={{ color: '#ef4444', fontSize: 12 }}>{record.last_error || '-'}</span>
        </Tooltip>
      ),
    },
    {
      title: '重试',
      dataIndex: 'retry_count',
      key: 'retry_count',
      width: 60,
      align: 'center',
    },
    {
      title: '下次重试',
      dataIndex: 'next_retry_at',
      key: 'next_retry_at',
      width: 145,
      render: (_dom, record) => fmtTime(record.next_retry_at),
    },
    {
      title: '入队时间',
      dataIndex: 'enqueued_at',
      key: 'enqueued_at',
      width: 145,
      render: (_dom, record) => fmtTime(record.enqueued_at),
    },
    {
      title: '入队人',
      dataIndex: 'enqueued_by_user',
      key: 'enqueued_by_user',
      width: 100,
      render: (_dom, record) => record.enqueued_by_user || <span style={{ color: '#94a3b8' }}>{record.enqueued_by || '-'}</span>,
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      fixed: 'right',
      render: (_dom, record) => (
        <Space size="small">
          <Button
            size="small"
            type="link"
            icon={<EyeOutlined />}
            onClick={() => setDetail(record)}
          >
            详情
          </Button>
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
        {stats && stats.by_type && stats.by_type.length > 0 && (
          <div style={{ marginTop: 16, borderTop: '1px dashed #e5e7eb', paddingTop: 12 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>按类型分布：</Text>
            <Space size={[8, 8]} wrap style={{ marginLeft: 8 }}>
              {stats.by_type.map((t) => (
                <Tooltip
                  key={t.writeback_type}
                  title={`待处理 ${t.pending} · 失败 ${t.failed} · 死信 ${t.dead}`}
                >
                  <Tag color="blue" style={{ marginRight: 0 }}>
                    {t.writeback_type}
                    <span style={{ color: '#64748b', marginLeft: 6, fontWeight: 600 }}>
                      待{t.pending} 败{t.failed} 死{t.dead}
                    </span>
                  </Tag>
                </Tooltip>
              ))}
            </Space>
          </div>
        )}
      </Card>

      <ProTable<QueueItem>
        headerTitle="回写队列"
        rowKey="id"
        columns={columns}
        actionRef={actionRef}
        request={fetchData}
        params={{ status: statusFilter }}
        loading={loading}
        search={false}
        scroll={{ x: 1600 }}
        toolBarRender={() => [
          <Select
            key="status"
            value={statusFilter}
            onChange={(v) => setStatusFilter(v)}
            style={{ width: 120 }}
            options={[
              { value: '', label: '全部' },
              { value: 'failed', label: '失败' },
              { value: 'dead', label: '死信' },
              { value: 'pending', label: '待处理' },
              { value: 'processing', label: '处理中' },
              { value: 'done', label: '完成' },
              { value: 'abandoned', label: '已放弃' },
            ]}
          />,
          <Button
            key="refresh"
            icon={<ReloadOutlined />}
            onClick={() => { fetchStats(); actionRef.current?.reload() }}
          >
            刷新
          </Button>,
        ]}
        pagination={{ defaultPageSize: 20, showSizeChanger: true }}
        size="small"
      />

      <Drawer
        title={detail ? `队列详情 #${detail.id}` : '队列详情'}
        open={!!detail}
        onClose={() => setDetail(null)}
        width={620}
        destroyOnClose
      >
        {detail && (
          <>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="状态" span={1}>
                {(() => {
                  const meta = STATUS_META[detail.status] || { color: 'default', label: detail.status }
                  return <Tag color={meta.color}>{meta.label}</Tag>
                })()}
              </Descriptions.Item>
              <Descriptions.Item label="类型" span={1}>
                <Tag color="blue">{detail.writeback_type}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="业务表" span={1}>
                <code>{detail.business_table}</code>
              </Descriptions.Item>
              <Descriptions.Item label="业务主键" span={1}>
                {detail.business_pk}
              </Descriptions.Item>
              <Descriptions.Item label="重试次数" span={1}>
                {detail.retry_count}
              </Descriptions.Item>
              <Descriptions.Item label="入队来源" span={1}>
                {detail.enqueued_by_user || detail.enqueued_by || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="入队时间" span={1}>
                {fmtTime(detail.enqueued_at)}
              </Descriptions.Item>
              <Descriptions.Item label="开始处理" span={1}>
                {fmtTime(detail.picked_at)}
              </Descriptions.Item>
              <Descriptions.Item label="下次重试" span={1}>
                {fmtTime(detail.next_retry_at)}
              </Descriptions.Item>
              <Descriptions.Item label="完成时间" span={1}>
                {fmtTime(detail.finished_at)}
              </Descriptions.Item>
            </Descriptions>

            <div style={{ marginTop: 16 }}>
              <Text type="secondary">目标键 (target_keys)</Text>
              <Paragraph style={{ marginTop: 4 }}>
                <pre style={{
                  background: '#f5f5f5', padding: 12, borderRadius: 6,
                  fontSize: 12, fontFamily: 'monospace', margin: 0, maxHeight: 200, overflow: 'auto',
                }}>
                  {JSON.stringify(detail.target_keys ?? {}, null, 2)}
                </pre>
              </Paragraph>
            </div>

            <div style={{ marginTop: 12 }}>
              <Text type="secondary">回写数据 (payload)</Text>
              <Paragraph style={{ marginTop: 4 }}>
                <pre style={{
                  background: '#f5f5f5', padding: 12, borderRadius: 6,
                  fontSize: 12, fontFamily: 'monospace', margin: 0, maxHeight: 240, overflow: 'auto',
                }}>
                  {JSON.stringify(detail.payload ?? {}, null, 2)}
                </pre>
              </Paragraph>
            </div>

            {detail.last_error && (
              <div style={{ marginTop: 12 }}>
                <Text type="danger">错误信息</Text>
                <Paragraph style={{ marginTop: 4 }}>
                  <pre style={{
                    background: '#fef2f2', padding: 12, borderRadius: 6, border: '1px solid #fecaca',
                    fontSize: 12, fontFamily: 'monospace', margin: 0, maxHeight: 240, overflow: 'auto',
                    color: '#ef4444', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                  }}>
                    {detail.last_error}
                  </pre>
                </Paragraph>
              </div>
            )}

            <div style={{ marginTop: 16, textAlign: 'right' }}>
              <Space>
                <Button
                  icon={<RedoOutlined />}
                  loading={retryingId === detail.id}
                  onClick={() => handleRetry(detail.id)}
                >
                  重试
                </Button>
                {detail.status === 'dead' && (
                  <Button danger onClick={() => { handleAbandon(detail.id); setDetail(null) }}>
                    放弃
                  </Button>
                )}
              </Space>
            </div>
          </>
        )}
        {!detail && <Empty />}
      </Drawer>
    </PageContainer>
  )
}
