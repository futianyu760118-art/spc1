import { useCallback, useEffect, useMemo, useState } from 'react'
import { Table, Tag, Button, message, Row, Col, Select, Input, Space } from 'antd'
import { ClearOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import type { SortOrder } from 'antd/es/table/interface'
import { exceptionApi } from '../../../services/api'
import { formatDate } from '../../../utils'

const STATUS_LABEL: Record<string, string> = {
  open: '待处理',
  in_progress: '处理中',
  closed: '已关闭',
}

const SOURCE_TYPE_LABEL: Record<string, string> = {
  risk_issue: '风险问题',
  quality_issue: '品质异常',
  process_exception: '工序异常',
}

const STATUS_ORDER: Record<string, number> = { open: 0, in_progress: 1, closed: 2 }
const DEFAULT_STATUS = 'open'
const DEFAULT_SORT_BY = 'open_count'
const DEFAULT_SORT_ORDER: 'asc' | 'desc' = 'desc'
const SOURCE_TYPE_OPTIONS = [
  { label: '风险问题', value: 'risk_issue' },
  { label: '品质异常', value: 'quality_issue' },
  { label: '工序异常', value: 'process_exception' },
]
const STATUS_OPTIONS = [
  { label: '待处理', value: 'open' },
  { label: '处理中', value: 'in_progress' },
  { label: '已关闭', value: 'closed' },
]
const STATUS_COLOR: Record<string, string> = {
  open: 'red',
  in_progress: 'orange',
  closed: 'green',
}

const renderCount = (value: number, color?: string) => (
  value > 0 ? <Tag color={color}>{value}</Tag> : <span style={{ color: '#94a3b8' }}>0</span>
)

export default function ClosureTracking() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [filterSourceType, setFilterSourceType] = useState<string | undefined>(undefined)
  const [filterStatus, setFilterStatus] = useState<string | undefined>(DEFAULT_STATUS)
  const [filterOwner, setFilterOwner] = useState<string | undefined>(undefined)
  const [ownerKeyword, setOwnerKeyword] = useState('')
  const [sortBy, setSortBy] = useState<string | undefined>(DEFAULT_SORT_BY)
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(DEFAULT_SORT_ORDER)
  const [personDetailMap, setPersonDetailMap] = useState<Record<string, any[]>>({})
  const [personDetailLoadingMap, setPersonDetailLoadingMap] = useState<Record<string, boolean>>({})
  const [detailFiltersMap, setDetailFiltersMap] = useState<Record<string, Record<string, any[] | null>>>({})
  const [detailSortMap, setDetailSortMap] = useState<Record<string, { field?: string; order?: 'ascend' | 'descend' }>>({})

  const getPersonDetailKey = useCallback((owner: string) => [
    owner || '__empty_owner__',
    filterSourceType || 'all_source_types',
    filterStatus || 'all_statuses',
  ].join('|'), [filterSourceType, filterStatus])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, any> = {}
      if (filterSourceType) params.source_type = filterSourceType
      if (filterStatus) params.status = filterStatus
      if (filterOwner) params.owner = filterOwner
      if (sortBy) params.sort_by = sortBy
      params.sort_order = sortOrder
      const res: any = await exceptionApi.getClosureTracking(params)
      setData(res.data)
    } catch (e: any) {
      message.error(e.message || '获取闭环跟踪数据失败')
    } finally {
      setLoading(false)
    }
  }, [filterSourceType, filterStatus, filterOwner, sortBy, sortOrder])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    setPersonDetailMap({})
    setPersonDetailLoadingMap({})
    setDetailFiltersMap({})
    setDetailSortMap({})
  }, [filterSourceType, filterStatus, filterOwner])

  const statCards = useMemo(() => data ? [
    { label: '待处理', value: data.total_open, color: '#e11d48' },
    { label: '处理中', value: data.total_in_progress, color: '#d97706' },
    { label: '已关闭', value: data.total_closed, color: '#10b981' },
    { label: '已超时', value: data.total_overdue, color: '#dc2626' },
  ] : [], [data])

  const getSortOrder = useCallback((field: string): SortOrder | undefined => {
    if (sortBy !== field) return undefined
    return sortOrder === 'asc' ? 'ascend' : 'descend'
  }, [sortBy, sortOrder])

  const typeColumns = useMemo(() => [
    {
      title: '异常类型',
      dataIndex: 'source_type',
      width: 140,
      sorter: true,
      sortOrder: getSortOrder('source_type'),
      render: (v: string) => SOURCE_TYPE_LABEL[v] || v,
    },
    { title: '待处理', dataIndex: 'open_count', width: 90, align: 'right' as const, sorter: true, sortOrder: getSortOrder('open_count'), render: (v: number) => renderCount(v, 'red') },
    { title: '处理中', dataIndex: 'in_progress_count', width: 90, align: 'right' as const, sorter: true, sortOrder: getSortOrder('in_progress_count'), render: (v: number) => renderCount(v, 'orange') },
    { title: '已关闭', dataIndex: 'closed_count', width: 90, align: 'right' as const, sorter: true, sortOrder: getSortOrder('closed_count'), render: (v: number) => renderCount(v, 'green') },
    { title: '已超时', dataIndex: 'overdue_count', width: 90, align: 'right' as const, sorter: true, sortOrder: getSortOrder('overdue_count'), render: (v: number) => renderCount(v, 'red') },
  ], [getSortOrder])

  const personColumns = useMemo(() => [
    {
      title: '责任人',
      dataIndex: 'owner',
      width: 140,
      sorter: true,
      sortOrder: getSortOrder('owner'),
      render: (v: string) => v || '未分配',
    },
    { title: '待处理', dataIndex: 'open_count', width: 90, align: 'right' as const, sorter: true, sortOrder: getSortOrder('open_count'), render: (v: number) => renderCount(v, 'red') },
    { title: '处理中', dataIndex: 'in_progress_count', width: 90, align: 'right' as const, sorter: true, sortOrder: getSortOrder('in_progress_count'), render: (v: number) => renderCount(v, 'orange') },
    { title: '已关闭', dataIndex: 'closed_count', width: 90, align: 'right' as const, sorter: true, sortOrder: getSortOrder('closed_count'), render: (v: number) => renderCount(v, 'green') },
    { title: '已超时', dataIndex: 'overdue_count', width: 90, align: 'right' as const, sorter: true, sortOrder: getSortOrder('overdue_count'), render: (v: number) => renderCount(v, 'red') },
  ], [getSortOrder])

  const handleTableChange = (_: any, __: any, sorter: any) => {
    const activeSorter = Array.isArray(sorter) ? sorter[0] : sorter
    if (activeSorter?.field && activeSorter?.order) {
      setSortBy(String(activeSorter.field))
      setSortOrder(activeSorter.order === 'ascend' ? 'asc' : 'desc')
    } else {
      setSortBy(DEFAULT_SORT_BY)
      setSortOrder(DEFAULT_SORT_ORDER)
    }
  }

  const applyOwnerFilter = useCallback((value: string) => {
    const nextValue = value.trim()
    setFilterOwner(nextValue || undefined)
  }, [])

  const resetFilters = () => {
    setFilterSourceType(undefined)
    setFilterStatus(DEFAULT_STATUS)
    setFilterOwner(undefined)
    setOwnerKeyword('')
    setSortBy(DEFAULT_SORT_BY)
    setSortOrder(DEFAULT_SORT_ORDER)
  }

  const loadPersonDetails = useCallback(async (owner: string) => {
    if (!owner) return
    const detailKey = getPersonDetailKey(owner)
    if (personDetailMap[detailKey]) return
    setPersonDetailLoadingMap(prev => ({ ...prev, [detailKey]: true }))
    try {
      const res: any = await exceptionApi.getClosureTrackingPersonDetails({
        owner,
        source_type: filterSourceType,
        status: filterStatus,
      })
      setPersonDetailMap(prev => ({ ...prev, [detailKey]: res.data || [] }))
    } catch (e: any) {
      message.error(e.message || '加载异常明细失败')
    } finally {
      setPersonDetailLoadingMap(prev => ({ ...prev, [detailKey]: false }))
    }
  }, [filterSourceType, filterStatus, getPersonDetailKey, personDetailMap])

  const buildTextSearchColumn = (title: string, field: string, width: number, render?: (v: any) => any) => ({
    title,
    dataIndex: field,
    width,
    sorter: (a: any, b: any) => String(a?.[field] || '').localeCompare(String(b?.[field] || '')),
    filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
      <div style={{ padding: 8 }}>
        <Input
          placeholder="筛选内容"
          value={selectedKeys[0]}
          onChange={e => setSelectedKeys(e.target.value ? [e.target.value] : [])}
          onPressEnter={() => confirm()}
          style={{ marginBottom: 8, display: 'block', width: 200 }}
        />
        <Space>
          <Button type="primary" size="small" onClick={() => confirm()} icon={<SearchOutlined />}>筛选</Button>
          <Button size="small" onClick={() => { clearFilters?.(); confirm() }}>重置</Button>
        </Space>
      </div>
    ),
    filterIcon: (filtered: boolean) => <SearchOutlined style={{ color: filtered ? '#1677ff' : undefined }} />,
    onFilter: (value: any, record: any) => String(record?.[field] || '').toLowerCase().includes(String(value || '').toLowerCase()),
    render: render || ((v: any) => v || '-'),
  })

  const buildDetailColumns = (rows: any[]) => {
    const uniqueFilters = (field: string) =>
      Array.from(new Set(rows.map(item => item?.[field]).filter(Boolean))).map(value => ({ text: String(value), value: String(value) }))

    return [
      {
        title: '异常类型',
        dataIndex: 'source_type',
        width: 120,
        filters: uniqueFilters('source_type'),
        onFilter: (value: any, record: any) => record.source_type === value,
        sorter: (a: any, b: any) => String(a?.source_type || '').localeCompare(String(b?.source_type || '')),
        render: (v: string) => SOURCE_TYPE_LABEL[v] || v,
      },
      buildTextSearchColumn('异常编号', 'source_no', 140),
      buildTextSearchColumn('异常描述', 'title', 220, (v: string | null) => <span title={v || ''}>{v || '-'}</span>),
      {
        title: '状态',
        dataIndex: 'status',
        width: 100,
        filters: uniqueFilters('status'),
        onFilter: (value: any, record: any) => record.status === value,
        sorter: (a: any, b: any) => (STATUS_ORDER[a?.status || ''] ?? 99) - (STATUS_ORDER[b?.status || ''] ?? 99),
        render: (v: string) => <Tag color={STATUS_COLOR[v]}>{STATUS_LABEL[v] || v}</Tag>,
      },
      buildTextSearchColumn('订单号', 'order_no', 160, (v: string | null) => v || '-'),
      {
        title: '创建时间',
        dataIndex: 'created_at',
        width: 160,
        sorter: (a: any, b: any) => new Date(a?.created_at || 0).getTime() - new Date(b?.created_at || 0).getTime(),
        render: (v: string) => (v ? formatDate(v) : '-'),
      },
    ]
  }

  const buildExpandedDetailTable = (record: any) => {
    const detailKey = getPersonDetailKey(record.owner)
    const detailRows = personDetailMap[detailKey] || []
    const localFilters = detailFiltersMap[detailKey] || {}
    const localSorter = detailSortMap[detailKey] || {}
    const columns = buildDetailColumns(detailRows).map((column: any) => ({
      ...column,
      filteredValue: localFilters[column.dataIndex] || null,
      sortOrder: localSorter.field === column.dataIndex ? localSorter.order : undefined,
    }))

    return (
      <Table
        rowKey={(r: any) => `${r.source_type}-${r.source_id}`}
        dataSource={detailRows}
        columns={columns}
        size="small"
        pagination={detailRows.length > 10 ? { pageSize: 10, showSizeChanger: false, size: 'small' } : false}
        loading={personDetailLoadingMap[detailKey]}
        locale={{ emptyText: personDetailLoadingMap[detailKey] ? '加载中...' : '暂无异常明细' }}
        tableLayout="fixed"
        scroll={{ x: 900 }}
        onChange={(_, filters, sorter: any) => {
          setDetailFiltersMap(prev => ({ ...prev, [detailKey]: filters as Record<string, any[] | null> }))
          setDetailSortMap(prev => ({ ...prev, [detailKey]: { field: sorter.field, order: sorter.order } }))
        }}
      />
    )
  }

  return (
    <div>
      <div className="card-modern" style={{ padding: '14px 16px', marginBottom: 16 }}>
        <Row gutter={[12, 12]} align="middle">
          <Col>
            <Select
              allowClear
              placeholder="异常类型"
              style={{ width: 140 }}
              value={filterSourceType}
              onChange={setFilterSourceType}
              options={SOURCE_TYPE_OPTIONS}
            />
          </Col>
          <Col>
            <Select
              allowClear
              placeholder="状态"
              style={{ width: 120 }}
              value={filterStatus}
              onChange={setFilterStatus}
              options={STATUS_OPTIONS}
            />
          </Col>
          <Col>
            <Input.Search
              placeholder="责任人"
              allowClear
              style={{ width: 180 }}
              value={ownerKeyword}
              onChange={e => {
                setOwnerKeyword(e.target.value)
                if (!e.target.value) setFilterOwner(undefined)
              }}
              onSearch={applyOwnerFilter}
              enterButton={<SearchOutlined />}
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Button icon={<ClearOutlined />} onClick={resetFilters}>重置</Button>
          </Col>
          <Col>
            <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
          </Col>
        </Row>
      </div>

      {data && (
        <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
          {statCards.map(({ label, value, color }) => (
            <div key={label} className="card-modern" style={{ flex: 1, padding: '12px 20px' }}>
              <div style={{ color: '#94a3b8', fontSize: 14, marginBottom: 4 }}>{label}</div>
              <div style={{ fontSize: 28, fontWeight: 700, color }}>{value}</div>
            </div>
          ))}
        </div>
      )}

      <div className="card-modern" style={{ padding: 16, marginBottom: 16 }}>
        <h3 style={{ marginBottom: 12, fontSize: 16, fontWeight: 600 }}>按异常类型分布</h3>
        <Table
          rowKey="source_type"
          dataSource={data?.by_type || []}
          columns={typeColumns}
          loading={loading}
          size="small"
          pagination={false}
          tableLayout="fixed"
          scroll={{ x: 520 }}
          onChange={handleTableChange}
        />
      </div>

      <div className="card-modern" style={{ padding: 16 }}>
        <h3 style={{ marginBottom: 12, fontSize: 16, fontWeight: 600 }}>按责任人分布</h3>
        <Table
          rowKey="owner"
          dataSource={data?.by_person || []}
          columns={personColumns}
          loading={loading}
          size="small"
          pagination={false}
          tableLayout="fixed"
          scroll={{ x: 560 }}
          onChange={handleTableChange}
          expandable={{
            expandRowByClick: false,
            onExpand: (expanded, record: any) => {
              if (expanded) loadPersonDetails(record.owner)
            },
            expandedRowRender: buildExpandedDetailTable,
          }}
        />
      </div>
    </div>
  )
}
