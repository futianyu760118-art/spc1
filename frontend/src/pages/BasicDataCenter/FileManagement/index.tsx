import { useEffect, useState } from 'react'
import {
  Table, Tag, Button, Space, Input, Row, Col, Card, message, Popconfirm,
  Modal, InputNumber, Image,
} from 'antd'
import { ReloadOutlined, SearchOutlined, DeleteOutlined, ClearOutlined } from '@ant-design/icons'
import { fileApi } from '../../../services/api'
import PermButton from '../../../components/PermButton'
import { useAuthStore } from '../../../store/auth'

const namespaceLabel: Record<string, string> = {
  feedback: '问题反馈',
  quality: '品质异常',
  npi: 'NPI',
  misc: '其他',
}

function formatSize(bytes: number) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`
}

export default function FileManagement() {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [stats, setStats] = useState<any>({ total_count: 0, total_size: 0, orphan_count: 0, uploaded_last_7d: 0 })
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })
  const [keyword, setKeyword] = useState<string>('')
  const [sortInfo, setSortInfo] = useState<{ sort_by?: string; sort_order?: string }>({})
  const [filters, setFilters] = useState<Record<string, string>>({})

  const [cleanupOpen, setCleanupOpen] = useState(false)
  const [cleanupDays, setCleanupDays] = useState(7)
  const [cleaning, setCleaning] = useState(false)
  const hasPermission = useAuthStore(s => s.hasPermission)
  const canCreate = hasPermission('basicdata.files', 'create')
  const canDelete = hasPermission('basicdata.files', 'delete')

  const fetchData = async (page = pagination.current, pageSize = pagination.pageSize, kw?: string) => {
    setLoading(true)
    try {
      const params: any = { page, page_size: pageSize }
      const k = (kw !== undefined ? kw : keyword).trim()
      if (k) params.keyword = k
      if (sortInfo.sort_by) params.sort_by = sortInfo.sort_by
      if (sortInfo.sort_order) params.sort_order = sortInfo.sort_order
      Object.entries(filters).forEach(([key, val]) => { if (val) params[key] = val })
      const res: any = await fileApi.list(params)
      setData(res.data?.items || [])
      setPagination({ current: res.data?.page || 1, pageSize: res.data?.page_size || 20, total: res.data?.total || 0 })
    } catch {
      // 错误已由全局拦截器提示
    } finally {
      setLoading(false)
    }
  }

  const fetchStats = async () => {
    try {
      const res: any = await fileApi.stats()
      setStats(res.data || stats)
    } catch { /* ignore */ }
  }

  useEffect(() => { fetchData(1); fetchStats() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // 自动搜索（输入即搜，300ms 防抖）
  useEffect(() => {
    const t = setTimeout(() => { fetchData(1, pagination.pageSize, keyword) }, 300)
    return () => clearTimeout(t)
  }, [keyword]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleDelete = async (id: number) => {
    try {
      await fileApi.remove(id)
      message.success('已删除')
      fetchData()
      fetchStats()
    } catch (e: any) {
      // 错误已由全局拦截器提示
    }
  }

  const handleCleanup = async () => {
    try {
      setCleaning(true)
      const res: any = await fileApi.cleanupOrphans(cleanupDays)
      message.success(`已清理 ${res.data?.cleaned || 0} 个孤儿文件`)
      setCleanupOpen(false)
      fetchData()
      fetchStats()
    } catch (e: any) {
      // 错误已由全局拦截器提示
    } finally {
      setCleaning(false)
    }
  }

  const handleTableChange = (_pag: any, tableFilters: any, sorter: any) => {
    const sortField = sorter.field
    const sortOrder = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : undefined
    setSortInfo({ sort_by: sortField, sort_order: sortOrder })
    const newFilters: Record<string, string> = {}
    if (tableFilters.mime?.length) newFilters.mime = tableFilters.mime.join(',')
    if (tableFilters.namespace?.length) newFilters.namespace = tableFilters.namespace.join(',')
    if (tableFilters.uploader_name?.length) newFilters.uploader = tableFilters.uploader_name.join(',')
    if (tableFilters.is_orphan?.length) newFilters.is_orphan = tableFilters.is_orphan[0]
    setFilters(newFilters)
    fetchData(1, pagination.pageSize)
  }

  const uniqueValues = (key: string) => Array.from(new Set(data.map((r: any) => r[key]).filter(Boolean))).map(v => ({ text: String(v), value: v }))
  const mimeFilters = Array.from(new Set(data.map((r: any) => r.mime).filter(Boolean))).map(v => ({ text: String(v), value: v }))

  const columns: any[] = [
    {
      title: '预览', key: 'thumb', width: 60,
      render: (_: any, r: any) => r.mime?.startsWith('image/')
        ? <Image src={r.url} alt={r.name} width={40} height={40} style={{ objectFit: 'cover', borderRadius: 4, cursor: 'zoom-in' }} preview={{ mask: '预览' }} />
        : <span style={{ color: '#94a3b8' }}>—</span>,
    },
    {
      title: '文件名', dataIndex: 'name', key: 'name', ellipsis: true,
      render: (v: string, r: any) => <a href={r.url} target="_blank" rel="noreferrer">{v}</a>,
      sorter: true,
    },
    {
      title: '大小', dataIndex: 'size', key: 'size', width: 100,
      render: (v: number) => formatSize(v || 0),
      sorter: true,
    },
    {
      title: '类型', dataIndex: 'mime', key: 'mime', width: 160, ellipsis: true,
      sorter: true,
      filters: mimeFilters,
      filterSearch: true,
    },
    {
      title: '业务域', dataIndex: 'namespace', key: 'namespace', width: 100,
      render: (v: string) => <Tag>{namespaceLabel[v] || v}</Tag>,
      sorter: true,
      filters: Object.entries(namespaceLabel).map(([k, v]) => ({ text: v, value: k })),
    },
    {
      title: '业务ID', dataIndex: 'biz_ref', key: 'biz_ref', width: 100,
      sorter: true,
    },
    {
      title: '上传人', dataIndex: 'uploader_name', key: 'uploader_name', width: 100,
      sorter: true,
      filters: uniqueValues('uploader_name'),
      filterSearch: true,
    },
    {
      title: '上传时间', dataIndex: 'uploaded_at', key: 'uploaded_at', width: 160,
      render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-',
      sorter: true,
    },
    {
      title: '状态', dataIndex: 'is_orphan', key: 'is_orphan', width: 90,
      render: (v: boolean) => v
        ? <Tag color="orange">孤儿</Tag>
        : <Tag color="green">已引用</Tag>,
      filters: [{ text: '孤儿', value: true }, { text: '已引用', value: false }],
    },
    {
      title: '操作', key: 'actions', width: 100, fixed: 'right',
      render: (_: any, r: any) => (
        <Space size="small">
          <Popconfirm title="确定删除？删除后文件不可恢复" onConfirm={() => handleDelete(r.id)} disabled={!canDelete}>
            <PermButton permResource="basicdata.files" permAction="delete" type="link" size="small" danger icon={<DeleteOutlined />}>删除</PermButton>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><div style={{ color: '#64748b' }}>总文件数</div><div style={{ fontSize: 24, fontWeight: 600 }}>{stats.total_count}</div></Card></Col>
        <Col span={6}><Card><div style={{ color: '#64748b' }}>总占用</div><div style={{ fontSize: 24, fontWeight: 600 }}>{formatSize(stats.total_size)}</div></Card></Col>
        <Col span={6}><Card><div style={{ color: '#fa8c16' }}>孤儿文件</div><div style={{ fontSize: 24, fontWeight: 600 }}>{stats.orphan_count}</div></Card></Col>
        <Col span={6}><Card><div style={{ color: '#52c41a' }}>7天上传</div><div style={{ fontSize: 24, fontWeight: 600 }}>{stats.uploaded_last_7d}</div></Card></Col>
      </Row>

      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col flex="auto">
            <Input
              prefix={<SearchOutlined />}
              placeholder="搜索文件名/上传人"
              allowClear
              size="middle"
              value={keyword}
              onChange={e => setKeyword(e.target.value)}
            />
          </Col>
          <Col>
            <Space>
              <PermButton permResource="basicdata.files" permAction="delete" icon={<ClearOutlined />} onClick={() => setCleanupOpen(true)}>清理孤儿</PermButton>
              <Button icon={<ReloadOutlined />} onClick={() => { fetchData(); fetchStats() }}>刷新</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern">
        <Image.PreviewGroup>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="id"
          loading={loading}
          size="small"
          scroll={{ x: 1280 }}
          onChange={handleTableChange}
          pagination={{
            ...pagination,
            showSizeChanger: true,
            showTotal: (total: number) => `共 ${total} 条`,
            onChange: (page, pageSize) => fetchData(page, pageSize),
            pageSizeOptions: ['20', '50', '100'],
          }}
        />
        </Image.PreviewGroup>
      </div>

      <Modal
        title="清理孤儿文件"
        open={cleanupOpen}
        onOk={handleCleanup}
        confirmLoading={cleaning}
        onCancel={() => setCleanupOpen(false)}
        okText="确认清理"
        okButtonProps={{ danger: true }}
        width={420}
      >
        <p>将清理 <b>{cleanupDays}</b> 天前未被业务引用的孤儿文件，操作不可撤销。</p>
        <Space>
          <span>天数：</span>
          <InputNumber min={0} max={365} value={cleanupDays} onChange={v => setCleanupDays(Number(v) || 0)} />
        </Space>
      </Modal>
    </div>
  )
}
