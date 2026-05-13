import React, { useState, useEffect, useCallback } from 'react'
import { Table, Card, Row, Col, Input, Select, Button, Tag, Progress, Tooltip, message, Switch } from 'antd'
import { SearchOutlined, ShoppingOutlined, PieChartOutlined, WarningOutlined, ExclamationCircleOutlined, CheckCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import { materialApi } from '@/services/api'

interface MaterialItem {
  material_code: string
  material_name: string | null
  supplier_name: string | null
  order_qty: number | null
  received_qty: number | null
  eta: string | null
  actual_arrival_date: string | null
  inspection_date: string | null
  status: string
  is_stagnant: boolean
  stagnant_qty: number | null
}

interface KitItem {
  order_no: string
  total_materials: number
  received_materials: number
  inspected_materials: number
  pending_inspection: number
  stagnant_materials: number
  kit_rate: number
  risk_level: string
  promised_date: string | null
  materials?: MaterialItem[]
}

const RISK_COLOR: Record<string, string> = { red: '#e11d48', yellow: '#f59e0b', green: '#16a34a' }
const RISK_LABEL: Record<string, string> = { red: '缺料严重', yellow: '部分齐套', green: '齐套' }

const MATERIAL_STATUS: Record<string, { label: string; color: string }> = {
  inspected: { label: '已检验', color: 'success' },
  arrived: { label: '已到料', color: 'processing' },
  overdue: { label: '逾期未到', color: 'error' },
  pending: { label: '待到料', color: 'default' },
}

export default function KitAnalysis() {
  const [data, setData] = useState<KitItem[]>([])
  const [loading, setLoading] = useState(false)
  const [orderNo, setOrderNo] = useState('')
  const [onlyPendingShipment, setOnlyPendingShipment] = useState(true)
  const [riskLevelFilter, setRiskLevelFilter] = useState<string | null>(null)
  const [expandedKeys, setExpandedKeys] = useState<string[]>([])
  const [sortBy, setSortBy] = useState<string>('')
  const [sortOrder, setSortOrder] = useState<string>('')
  const [materialsLoading, setMaterialsLoading] = useState<Record<string, boolean>>({})
  const [materialFilters, setMaterialFilters] = useState<Record<string, { status?: string; supplier?: string; sortBy?: string; sortOrder?: string }>>({})
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })
  const [statistics, setStatistics] = useState({ redCount: 0, yellowCount: 0, greenCount: 0, avgKitRate: 0 })

  const load = useCallback(async (page?: number, pageSize?: number) => {
    setLoading(true)
    try {
      const currentPage = page || pagination.current
      const currentPageSize = pageSize || pagination.pageSize
      const res: any = await materialApi.getKitAnalysis({
        ...(orderNo ? { order_no: orderNo } : {}),
        ...(sortBy ? { sort_by: sortBy, sort_order: sortOrder || 'asc' } : {}),
        ...(riskLevelFilter ? { risk_level: riskLevelFilter } : {}),
        only_pending_shipment: onlyPendingShipment,
        page: currentPage,
        page_size: currentPageSize,
      })
      setData(res.data.items)
      setPagination(prev => ({ ...prev, total: res.data.total, current: currentPage, pageSize: currentPageSize }))
      setStatistics({
        redCount: res.data.statistics?.red_count || 0,
        yellowCount: res.data.statistics?.yellow_count || 0,
        greenCount: res.data.statistics?.green_count || 0,
        avgKitRate: res.data.statistics?.avg_kit_rate || 0,
      })
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setLoading(false)
    }
  }, [orderNo, sortBy, sortOrder, pagination.current, pagination.pageSize, onlyPendingShipment, riskLevelFilter])

  const handlePaginationChange = useCallback((page: number, pageSize: number) => {
    setPagination(prev => ({ ...prev, current: page, pageSize }))
    // Trigger load with new pagination values
    load(page, pageSize)
  }, [load])

  const handleFilterChange = useCallback(() => {
    setPagination(prev => ({ ...prev, current: 1 }))
  }, [])

  const handlePendingShipmentToggle = useCallback((checked: boolean) => {
    setOnlyPendingShipment(checked)
    handleFilterChange()
  }, [handleFilterChange])

  const loadMaterials = useCallback(async (orderNo: string, statusFilter?: string[], supplierFilter?: string, sortBy?: string, sortOrder?: string) => {
    setMaterialsLoading(prev => ({ ...prev, [orderNo]: true }))
    try {
      const res: any = await materialApi.getOrderMaterials(orderNo, {
        ...(statusFilter && statusFilter.length > 0 ? { status: statusFilter.join(',') } : {}),
        ...(supplierFilter ? { supplier: supplierFilter } : {}),
        ...(sortBy ? { sort_by: sortBy, sort_order: sortOrder || 'asc' } : {}),
      })
      setData(prev => prev.map(item =>
        item.order_no === orderNo ? { ...item, materials: res.data } : item
      ))
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setMaterialsLoading(prev => ({ ...prev, [orderNo]: false }))
    }
  }, [])

  const handleExpand = useCallback(async (expanded: boolean, record: KitItem) => {
    if (expanded && !record.materials) {
      const filters = materialFilters[record.order_no] || {}
      await loadMaterials(record.order_no, filters.status ? [filters.status] : undefined, filters.supplier, filters.sortBy, filters.sortOrder)
    }
  }, [loadMaterials, materialFilters])

  const handleMaterialFilterChange = useCallback((orderNo: string, key: string, value: string) => {
    setMaterialFilters(prev => ({
      ...prev,
      [orderNo]: { ...prev[orderNo], [key]: value }
    }))
    // 清除物料缓存，强制重新加载
    setData(prev => prev.map(item =>
      item.order_no === orderNo ? { ...item, materials: undefined } : item
    ))
  }, [])

  const handleMaterialSortChange = useCallback((orderNo: string, sortField: string, sortOrder: string) => {
    setMaterialFilters(prev => ({
      ...prev,
      [orderNo]: { ...prev[orderNo], sortBy: sortField, sortOrder }
    }))
    // 清除物料缓存，强制重新加载
    setData(prev => prev.map(item =>
      item.order_no === orderNo ? { ...item, materials: undefined } : item
    ))
  }, [])

  useEffect(() => { load() }, [load])

  const materialColumns = [
    {
      title: '物料代码', dataIndex: 'material_code', width: 180, ellipsis: true, sorter: true,
      render: (v: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span>,
    },
    { title: '物料名称', dataIndex: 'material_name', width: 180, ellipsis: true, sorter: true },
    {
      title: '供应商', dataIndex: 'supplier_name', width: 130, ellipsis: true, sorter: true,
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8 }}>
          <Input
            placeholder="供应商名称"
            value={selectedKeys[0]}
            onChange={e => setSelectedKeys(e.target.value ? [e.target.value] : [])}
            onPressEnter={confirm}
            style={{ width: 188, marginBottom: 8, display: 'block' }}
          />
          <Button type="primary" onClick={confirm} size="small" style={{ width: 90, marginRight: 8 }}>
            搜索
          </Button>
          <Button onClick={clearFilters} size="small" style={{ width: 90 }}>
            重置
          </Button>
        </div>
      ),
      filterIcon: (filtered: boolean) => <SearchOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
    },
    {
      title: '需求量', dataIndex: 'order_qty', width: 80, sorter: true,
      render: (v: number | null) => v ?? '-',
    },
    {
      title: '收料量', dataIndex: 'received_qty', width: 80, sorter: true,
      render: (v: number | null) => v != null ? <span style={{ color: '#16a34a' }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>0</span>,
    },
    {
      title: 'ETA', dataIndex: 'eta', width: 100, sorter: true,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '实际到料时间', dataIndex: 'actual_arrival_date', width: 120, sorter: true,
      render: (v: string | null) => v ? <span style={{ color: '#16a34a' }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '检验日期', dataIndex: 'inspection_date', width: 100, sorter: true,
      render: (v: string | null) => v ? <span style={{ color: '#6366f1' }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '状态', dataIndex: 'status', width: 90, sorter: true,
      filters: [
        { text: '已检验', value: 'inspected' },
        { text: '已到料', value: 'arrived' },
        { text: '逾期未到', value: 'overdue' },
        { text: '待到料', value: 'pending' },
      ],
      filterMultiple: true,
      render: (v: string) => {
        const s = MATERIAL_STATUS[v] || { label: v, color: 'default' }
        return <Tag color={s.color}>{s.label}</Tag>
      },
    },
    {
      title: '呆滞', dataIndex: 'is_stagnant', width: 80, sorter: true,
      render: (v: boolean, row: MaterialItem) => {
        if (!v) return <span style={{ color: '#cbd5e1' }}>-</span>
        return <Tooltip title={`超量 ${row.stagnant_qty}，收料${row.received_qty} > 需求${row.order_qty}`}><Tag color="warning">呆滞 +{row.stagnant_qty}</Tag></Tooltip>
      },
    },
  ]

  const columns = [
    {
      title: '订单号',
      dataIndex: 'order_no',
      key: 'order_no',
      width: 150,
      fixed: 'left' as const,
      sorter: true,
    },
    {
      title: '合同交期',
      dataIndex: 'promised_date',
      key: 'promised_date',
      width: 120,
      sorter: true,
      render: (date: string | null) => date || '-',
    },
    {
      title: '齐套率', dataIndex: 'kit_rate', width: 180, sorter: true,
      render: (v: number, row: KitItem) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Progress
            percent={Math.round(v * 100)}
            size="small"
            style={{ width: 120 }}
            strokeColor={RISK_COLOR[row.risk_level]}
            showInfo={false}
          />
          <span style={{ color: RISK_COLOR[row.risk_level], fontWeight: 600, fontSize: 13 }}>
            {Math.round(v * 100)}%
          </span>
        </div>
      ),
    },
    {
      title: '物料数', dataIndex: 'total_materials', width: 80, sorter: true,
      render: (v: number) => v,
    },
    {
      title: '已到料', dataIndex: 'received_materials', width: 80, sorter: true,
      render: (v: number) => <span style={{ color: '#16a34a' }}>{v}</span>,
    },
    {
      title: '已检验', dataIndex: 'inspected_materials', width: 80, sorter: true,
      render: (v: number) => <span style={{ color: '#6366f1' }}>{v}</span>,
    },
    {
      title: '待检验', dataIndex: 'pending_inspection', width: 80, sorter: true,
      render: (v: number) => v > 0 ? <span style={{ color: '#f59e0b' }}>{v}</span> : <span style={{ color: '#94a3b8' }}>0</span>,
    },
    {
      title: '缺料物料', width: 80, sorter: true,
      render: (_: any, row: KitItem) => {
        const shortage = row.total_materials - row.received_materials
        return shortage > 0 ? <span style={{ color: '#e11d48', fontWeight: 600 }}>{shortage}</span> : <span style={{ color: '#16a34a' }}>0</span>
      },
    },
    {
      title: '呆滞物料', dataIndex: 'stagnant_materials', width: 80, sorter: true,
      render: (v: number) => v > 0 ? <span style={{ color: '#d97706', fontWeight: 600 }}>{v}</span> : <span style={{ color: '#94a3b8' }}>0</span>,
    },
    {
      title: '风险等级', dataIndex: 'risk_level', width: 90, sorter: true,
      filters: [
        { text: '缺料严重', value: 'red' },
        { text: '部分齐套', value: 'yellow' },
        { text: '齐套', value: 'green' },
      ],
      render: (v: string) => (
        <Tag color={v === 'red' ? 'error' : v === 'yellow' ? 'warning' : 'success'}>
          {RISK_LABEL[v] || v}
        </Tag>
      ),
    },
  ]

  return (
    <div>
      {/* 统计卡 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { title: '订单总数', value: pagination.total, icon: <ShoppingOutlined />, color: '#6366f1' },
          { title: '平均齐套率', value: `${statistics.avgKitRate}%`, icon: <PieChartOutlined />, color: '#16a34a' },
          { title: '缺料严重(齐套率<80%)', value: statistics.redCount, icon: <WarningOutlined />, color: '#e11d48' },
          { title: '部分齐套(80%-99%)', value: statistics.yellowCount, icon: <ExclamationCircleOutlined />, color: '#f59e0b' },
          { title: '已齐套(100%)', value: statistics.greenCount, icon: <CheckCircleOutlined />, color: '#16a34a' },
        ].map((card, i) => (
          <Col flex={1} key={i}>
            <Card size="small" className="card-modern" style={{ padding: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ width: 44, height: 44, borderRadius: 10, background: `${card.color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, color: card.color }}>
                  {card.icon}
                </div>
                <div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}>{card.value}</div>
                  <div style={{ fontSize: 12, color: '#64748b' }}>{card.title}</div>
                </div>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <Input
              prefix={<SearchOutlined />}
              placeholder="订单号"
              value={orderNo}
              onChange={e => { setOrderNo(e.target.value); handleFilterChange() }}
              style={{ width: 160 }}
              allowClear
            />
          </Col>
          <Col>
            <Switch
              checked={onlyPendingShipment}
              onChange={handlePendingShipmentToggle}
              checkedChildren="仅未发货"
              unCheckedChildren="全部"
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Button icon={<ReloadOutlined />} onClick={() => load()}>刷新</Button>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey="order_no"
          dataSource={data}
          columns={columns}
          loading={loading}
          size="small"
          scroll={{ x: 720 }}
          expandable={{
            expandedRowKeys: expandedKeys,
            onExpandedRowsChange: (keys) => setExpandedKeys(keys as string[]),
            onExpand: handleExpand,
            expandedRowRender: (row: KitItem) => (
              <div style={{ padding: '8px 0' }}>
                <Table
                  rowKey="material_code"
                  dataSource={row.materials || []}
                  columns={materialColumns}
                  pagination={false}
                  size="small"
                  scroll={{ x: 900 }}
                  loading={materialsLoading[row.order_no]}
                  onChange={(_pagination, tableFilters: any, sorter: any) => {
                    const sortField = sorter.field as string | undefined
                    const sortDir = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : ''

                    // Handle filters
                    const statusFilter = tableFilters.status || []
                    const supplierFilter = tableFilters.supplier_name?.[0]
                    handleMaterialFilterChange(row.order_no, 'status', statusFilter.length > 0 ? statusFilter[0] : '')
                    handleMaterialFilterChange(row.order_no, 'supplier', supplierFilter || '')
                    handleMaterialSortChange(row.order_no, sortField || '', sortDir)

                    // Load materials with current filters and sort
                    loadMaterials(row.order_no, statusFilter.length > 0 ? statusFilter : undefined, supplierFilter, sortField || '', sortDir)
                  }}
                />
              </div>
            ),
          }}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showTotal: t => `共 ${t} 单`,
            showSizeChanger: true,
            onChange: handlePaginationChange,
            onShowSizeChange: handlePaginationChange,
          }}
          onChange={(_pagination, tableFilters: any, sorter: any) => {
            const sortField = sorter.field as string | undefined
            const sortDir = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : ''
            setSortBy(sortField || '')
            setSortOrder(sortDir)

            // Handle risk_level filter
            const riskFilter = tableFilters.risk_level?.[0] || null
            setRiskLevelFilter(riskFilter)

            handleFilterChange()
          }}
        />
      </div>
    </div>
  )
}
