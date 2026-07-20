import { useState, useEffect, useCallback, useMemo } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import {
  Table, Input, Button, Space, Tag, message, Modal, Card, Row, Col,
  InputNumber, Checkbox, Spin, Popover, Tour, Drawer, Empty, Tooltip, DatePicker, Segmented, Badge,
} from 'antd'
import { SearchOutlined, ReloadOutlined, CheckCircleOutlined, StopOutlined, ArrowLeftOutlined, SaveOutlined, QuestionCircleOutlined, HistoryOutlined, UnorderedListOutlined, PlusOutlined } from '@ant-design/icons'
import { useAntTableQuery } from '@/hooks/useAntTableQuery'
import { materialApi } from '@/services/api'
import { formatDateTime } from '@/utils'
import { useUiPreferencesStore } from '@/store/uiPreferences'
import { useStockCheckPoolStore } from '@/store/stockCheckPool'
import { stockCheckIntroSteps, stockCheckDetailSteps, stockCheckManualDetailSteps, STOCK_CHECK_INTRO_TOUR_ID, STOCK_CHECK_DETAIL_TOUR_ID, STOCK_CHECK_MANUAL_DETAIL_TOUR_ID } from './StockCheckTour'
import MaterialPickerModal from './MaterialPickerModal'

interface StockCheckItem {
  id: number
  check_id: number
  line_no?: string | null
  material_id?: number | null
  material_code?: string | null
  material_name?: string | null
  spec_model?: string | null
  unit?: string | null
  req_qty?: number | null
  system_qty?: number | null
  actual_qty?: number | null
  diff_qty?: number | null
  is_checked?: number | null
  checked_at?: string | null
  checked_by?: string | null
  remark?: string | null
}

interface StockCheck {
  id: number
  check_no: string
  order_no?: string | null
  title?: string | null
  check_type?: string | null
  status?: string | null
  check_date?: string | null
  total_materials?: number | null
  checked_materials?: number | null
  total_diff_qty?: number | null
  created_by?: string | null
  checked_by?: string | null
  created_at?: string | null
  completed_at?: string | null
  remark?: string | null
  items?: StockCheckItem[]
}

interface MaterialCandidate {
  erp_material_id: number
  material_code?: string | null
  material_name?: string | null
  spec_model?: string | null
  unit?: string | null
  system_qty?: number | null
}

interface MaterialHistoryItem {
  check_no: string
  order_no: string
  customer?: string | null
  status: string
  check_date?: string | null
  completed_at?: string | null
  actual_qty?: number | null
  created_at?: string | null
  created_by?: string | null
}

interface MaterialOrderUsage {
  order_no: string
  line_no: string
  customer?: string | null
  product_code?: string | null
  product_name?: string | null
  order_qty?: number | null
  bom_no?: string | null
  standard_qty?: number | null
  req_qty?: number | null
  promised_date?: string | null
  status?: string | null
  order_nature?: string | null
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  open: { label: '待盘点', color: 'default' },
  in_progress: { label: '进行中', color: 'processing' },
  completed: { label: '已完成', color: 'success' },
  cancelled: { label: '已取消', color: 'error' },
}

export default function StockCheckPage() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const poolCount = useStockCheckPoolStore((s) => s.items.length)
  const poolRemove = useStockCheckPoolStore((s) => s.remove)
  const [orderNo, setOrderNo] = useState<string>(params.get('orderNo') || '')
  const [checkIdParam, setCheckIdParam] = useState<number | null>(() => {
    const v = params.get('checkId')
    return v ? Number(v) : null
  })
  const [searchText, setSearchText] = useState<string>('')

  const [activeCheck, setActiveCheck] = useState<StockCheck | null>(null)
  const [items, setItems] = useState<StockCheckItem[]>([])
  const [loading, setLoading] = useState(false)
  const [savingAll, setSavingAll] = useState(false)
  const [dateRange, setDateRange] = useState<[string?, string?]>([])
  const [checkTypeFilter, setCheckTypeFilter] = useState<string>('all')
  const [pickerOpen, setPickerOpen] = useState(false)
  const [creating, setCreating] = useState(false)

  const [orderUsageCache, setOrderUsageCache] = useState<Record<number, { total: number; items: MaterialOrderUsage[]; loading: boolean }>>({})
  const [orderUsagePage, setOrderUsagePage] = useState<Record<number, { page: number; page_size: number; keyword: string }>>({})

  const [usageModalOpen, setUsageModalOpen] = useState(false)
  const [usageMaterial, setUsageMaterial] = useState<StockCheckItem | null>(null)

  const loadCheck = useCallback(async (checkId: number) => {
    setLoading(true)
    try {
      const res: any = await materialApi.getStockCheck(checkId)
      const c: StockCheck = res.data
      setActiveCheck(c)
      setItems(c.items || [])
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '加载盘点单失败')
    } finally {
      setLoading(false)
    }
  }, [])

  const STATUS_OPTIONS = [
    { text: '待盘点', value: 'open' },
    { text: '进行中', value: 'in_progress' },
    { text: '已完成', value: 'completed' },
    { text: '已取消', value: 'cancelled' },
  ]

  const {
    tableProps: recentTableProps,
    searchInput: recentSearchInput,
    reload: reloadRecentList,
    filters: recentFilters,
  } = useAntTableQuery({
    initialFilters: { status: ['open', 'in_progress', 'completed'] },
    fetchData: async (params) => {
      const res: any = await materialApi.getRecentStockChecks({
        page: params.page,
        page_size: params.page_size,
        keyword: params.keyword,
        sort_by: params.sort_by,
        sort_order: params.sort_order,
        status: params.status,
        check_type: checkTypeFilter === 'all' ? undefined : checkTypeFilter,
        date_from: params.date_from,
        date_to: params.date_to,
      })
      return { items: res.data?.items || [], total: res.data?.total || 0 }
    },
    filterToQuery: (filters) => ({
      status: (filters.status as string[] | undefined)?.join(','),
      date_from: dateRange[0],
      date_to: dateRange[1],
    }),
    extraDeps: [dateRange, checkTypeFilter],
  })

  const handleCreate = useCallback(async (no: string) => {
    setLoading(true)
    try {
      const res: any = await materialApi.createStockCheckFromOrder(no, {})
      const c: StockCheck = res.data
      message.success(`已创建盘点单 ${c.check_no}`)
      setActiveCheck(c)
      setItems(c.items || [])
      setOrderNo(no)
      setCheckIdParam(null)
      setParams({ orderNo: no })
      reloadRecentList()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '创建盘点单失败')
    } finally {
      setLoading(false)
    }
  }, [reloadRecentList, setParams])

  const handleCreateFromMaterials = useCallback(async (selected: MaterialCandidate[], source: 'search' | 'pool') => {
    setCreating(true)
    try {
      const res: any = await materialApi.createStockCheckFromMaterials({
        material_ids: selected.map((s) => s.erp_material_id),
      })
      const c: StockCheck = res.data
      message.success(`已创建手动盘点单 ${c.check_no}`)
      if (source === 'pool') {
        poolRemove(selected.map((s) => s.erp_material_id))
      }
      setPickerOpen(false)
      setActiveCheck(c)
      setItems(c.items || [])
      setOrderNo('')
      setCheckIdParam(c.id)
      setParams({ checkId: String(c.id) })
      reloadRecentList()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '创建盘点单失败')
    } finally {
      setCreating(false)
    }
  }, [reloadRecentList, setParams, poolRemove])

  const handleSearch = useCallback(() => {
    if (searchText.trim()) {
      setParams({ orderNo: searchText.trim() })
      setOrderNo(searchText.trim())
    } else {
      setParams({})
      setOrderNo('')
      setActiveCheck(null)
      setItems([])
    }
  }, [searchText, setParams])

  useEffect(() => {
    if (checkIdParam) {
      if (!activeCheck || activeCheck.id !== checkIdParam) {
        loadCheck(checkIdParam)
      }
      return
    }
    if (orderNo && !activeCheck) {
      materialApi.getStockChecksByOrder(orderNo).then((res: any) => {
        const list: StockCheck[] = res.data || []
        const ongoing = list.find(c => c.status === 'in_progress' || c.status === 'open')
        if (ongoing) {
          loadCheck(ongoing.id)
        }
      }).catch(() => { /* silent */ })
    }
  }, [orderNo, checkIdParam, activeCheck, loadCheck])

  const newbieMode = useUiPreferencesStore(s => s.preferences?.newbie_mode !== false)
  const isManualDetail = activeCheck?.check_type === 'manual'
  const tourId = activeCheck
    ? (isManualDetail ? STOCK_CHECK_MANUAL_DETAIL_TOUR_ID : STOCK_CHECK_DETAIL_TOUR_ID)
    : STOCK_CHECK_INTRO_TOUR_ID
  const tourSteps = (activeCheck
    ? (isManualDetail ? stockCheckManualDetailSteps! : stockCheckDetailSteps!)
    : stockCheckIntroSteps!) ?? []
  const seenTour = useUiPreferencesStore(s => s.preferences?.['tours_seen']?.[tourId])
  const setUiFlag = useUiPreferencesStore(s => s.setFlag)
  const [tourOpen, setTourOpen] = useState(false)

  useEffect(() => {
    if (!newbieMode) return
    if (seenTour) return
    const t = setTimeout(() => setTourOpen(true), 500)
    return () => clearTimeout(t)
  }, [newbieMode, seenTour, tourId])

  const handleTourClose = useCallback(() => {
    const current = useUiPreferencesStore.getState().getFlag('tours_seen', {}) as Record<string, boolean>
    useUiPreferencesStore.getState().setFlag('tours_seen', { ...current, [tourId]: true })
    setTourOpen(false)
  }, [tourId])

  const handleHelpClick = useCallback(() => {
    setTourOpen(true)
  }, [])

  const handleNewbieToggle = useCallback((checked: boolean) => {
    setUiFlag('newbie_mode', checked)
  }, [setUiFlag])

  const [historyDrawerOpen, setHistoryDrawerOpen] = useState(false)
  const [historyMaterial, setHistoryMaterial] = useState<StockCheckItem | null>(null)
  const [historyItems, setHistoryItems] = useState<MaterialHistoryItem[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)

  const openMaterialHistory = useCallback(async (r: StockCheckItem) => {
    if (!r.material_id) {
      message.warning('该物料无 ID,无法查询历史')
      return
    }
    setHistoryMaterial(r)
    setHistoryDrawerOpen(true)
    setHistoryLoading(true)
    try {
      const res: any = await materialApi.getMaterialHistory({ material_id: r.material_id })
      setHistoryItems(res.data || [])
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '加载历史盘点失败')
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  const fetchOrderUsage = useCallback(async (materialId: number, page: number, keyword: string) => {
    setOrderUsageCache(prev => ({
      ...prev,
      [materialId]: { total: prev[materialId]?.total || 0, items: prev[materialId]?.items || [], loading: true },
    }))
    try {
      const res: any = await materialApi.getMaterialOrderUsage({
        material_id: materialId,
        page,
        page_size: 10,
        keyword: keyword || undefined,
        sort_by: 'req_qty',
        sort_order: 'desc',
      })
      const data = res.data || { total: 0, items: [] }
      setOrderUsageCache(prev => ({
        ...prev,
        [materialId]: { total: data.total || 0, items: data.items || [], loading: false },
      }))
    } catch (e: any) {
      setOrderUsageCache(prev => ({
        ...prev,
        [materialId]: { total: prev[materialId]?.total || 0, items: prev[materialId]?.items || [], loading: false },
      }))
      message.error(e?.response?.data?.detail || e.message || '加载订单需求失败')
    }
  }, [])

  const openUsageModal = useCallback((record: StockCheckItem) => {
    if (record.material_id == null) {
      message.warning('该物料无 ID,无法查询使用订单')
      return
    }
    setUsageMaterial(record)
    setUsageModalOpen(true)
    if (!orderUsageCache[record.material_id]) {
      setOrderUsagePage(prev => ({ ...prev, [record.material_id!]: { page: 1, page_size: 10, keyword: '' } }))
      fetchOrderUsage(record.material_id, 1, '')
    }
  }, [orderUsageCache, fetchOrderUsage])

  const closeUsageModal = useCallback(() => {
    setUsageModalOpen(false)
    setUsageMaterial(null)
  }, [])

  const saveItem = useCallback(async (item: StockCheckItem) => {
    try {
      const res: any = await materialApi.updateStockCheckItem(item.id, {
        actual_qty: item.actual_qty ?? undefined,
        is_checked: item.is_checked ?? 0,
        remark: item.remark ?? undefined,
      })
      const updated: StockCheckItem = res.data
      setItems(prev => prev.map(p => p.id === updated.id ? { ...p, ...updated } : p))
      const headRes: any = await materialApi.getStockCheck(updated.check_id)
      setActiveCheck(prev => prev ? { ...prev, ...headRes.data } : headRes.data)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '保存失败')
    }
  }, [])

  const saveAll = useCallback(async () => {
    if (!activeCheck) return
    setSavingAll(true)
    try {
      await materialApi.batchUpdateStockCheckItems(
        activeCheck.id,
        items.map(it => ({
          id: it.id,
          actual_qty: it.actual_qty ?? undefined,
          is_checked: it.is_checked ?? 0,
          remark: it.remark ?? undefined,
        })),
      )
      message.success('已批量保存')
      await loadCheck(activeCheck.id)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '批量保存失败')
    } finally {
      setSavingAll(false)
    }
  }, [activeCheck, items, loadCheck])

  const handleComplete = useCallback(async () => {
    if (!activeCheck) return
    const incomplete = items.filter(it => it.actual_qty == null)
    if (incomplete.length > 0) {
      message.error(`还有 ${incomplete.length} 行未录入实盘数,请先填写后再标记完成`)
      return
    }
    Modal.confirm({
      title: '标记完成',
      content: '完结后所有行将不可再修改,确认继续?',
      onOk: async () => {
        try {
          const res: any = await materialApi.completeStockCheck(activeCheck.id)
          setActiveCheck(res.data)
          setItems(res.data.items || [])
          message.success('已完结')
        } catch (e: any) {
          message.error(e?.response?.data?.detail || e.message || '完结失败')
        }
      },
    })
  }, [activeCheck, items])

  const handleCancel = useCallback(async () => {
    if (!activeCheck) return
    Modal.confirm({
      title: '取消盘点单',
      content: '确认取消该盘点单?',
      okType: 'danger',
      onOk: async () => {
        try {
          const res: any = await materialApi.cancelStockCheck(activeCheck.id)
          setActiveCheck(res.data)
          message.success('已取消')
        } catch (e: any) {
          message.error(e?.response?.data?.detail || e.message || '取消失败')
        }
      },
    })
  }, [activeCheck])

  const goBack = useCallback(() => {
    setActiveCheck(null)
    setItems([])
    setCheckIdParam(null)
    setParams({})
  }, [setParams])

  const updateItem = useCallback((id: number, patch: Partial<StockCheckItem>) => {
    setItems(prev => prev.map(p => p.id === id ? { ...p, ...patch } : p))
  }, [])

  const readonly = activeCheck?.status === 'completed' || activeCheck?.status === 'cancelled'

  const columns = useMemo(() => {
    const makeStringFilters = (key: keyof StockCheckItem) => {
      const set = new Set<string>()
      items.forEach(it => {
        const v = it[key]
        if (v != null && String(v).trim() !== '') set.add(String(v))
      })
      return Array.from(set).sort().map(v => ({ text: v, value: v }))
    }
    const stringCol = (
      key: keyof StockCheckItem,
      width: number,
      extra: Record<string, any> = {},
    ) => ({
      sorter: (a: any, b: any) => String(a[key] || '').localeCompare(String(b[key] || '')),
      filters: makeStringFilters(key),
      onFilter: (value: any, record: any) => record[key] === value,
      filterSearch: true,
      ...extra,
    })
    const numCol = (key: keyof StockCheckItem) => ({
      sorter: (a: any, b: any) => (Number(a[key]) || 0) - (Number(b[key]) || 0),
    })

    return [
      { title: '物料编码', dataIndex: 'material_code', width: 140, fixed: 'left' as const, ...stringCol('material_code', 140) },
      { title: '物料名称', dataIndex: 'material_name', width: 200, ellipsis: true, ...stringCol('material_name', 200) },
      { title: '规格', dataIndex: 'spec_model', width: 140, ellipsis: true, ...stringCol('spec_model', 140) },
      { title: '单位', dataIndex: 'unit', width: 60, ...stringCol('unit', 60) },
      {
        title: '即时库存', dataIndex: 'system_qty', width: 90, align: 'right' as const,
        ...numCol('system_qty'),
        render: (v: any) => v != null ? Number(v).toFixed(2) : '-',
      },
      {
        title: '盘点数', dataIndex: 'actual_qty', width: 120, align: 'right' as const,
        ...numCol('actual_qty'),
        render: (_: any, r: StockCheckItem) => (
          <InputNumber
            size="small"
            min={0}
            step={0.01}
            style={{ width: 100 }}
            disabled={readonly}
            value={r.actual_qty != null ? Number(r.actual_qty) : null}
            onChange={(v) => {
              const actual = v == null ? null : Number(v)
              const diff = actual != null && r.system_qty != null ? actual - Number(r.system_qty) : null
              updateItem(r.id, { actual_qty: actual, diff_qty: diff })
            }}
          />
        ),
      },
      {
        title: <span data-tour="stock-check-diff">差异</span>, dataIndex: 'diff_qty', width: 90, align: 'right' as const,
        ...numCol('diff_qty'),
        render: (v: any) => {
          if (v == null) return '-'
          const n = Number(v)
          const color = n > 0 ? '#16a34a' : n < 0 ? '#dc2626' : '#64748b'
          return <span style={{ color, fontWeight: 500 }}>{n.toFixed(2)}</span>
        },
      },
      {
        title: '已盘', dataIndex: 'is_checked', width: 70, align: 'center' as const,
        sorter: (a: any, b: any) => (Number(a.is_checked) || 0) - (Number(b.is_checked) || 0),
        filters: [
          { text: '已盘', value: 1 },
          { text: '未盘', value: 0 },
        ],
        onFilter: (value: any, record: any) => Number(record.is_checked) === Number(value),
        render: (_: any, r: StockCheckItem) => (
          <Checkbox
            disabled={readonly || r.actual_qty == null}
            checked={r.is_checked === 1}
            onChange={(e) => updateItem(r.id, { is_checked: e.target.checked ? 1 : 0 })}
          />
        ),
      },
      {
        title: '标记时间', dataIndex: 'checked_at', width: 160,
        sorter: (a: any, b: any) => {
          const ta = a.checked_at ? new Date(a.checked_at).getTime() : 0
          const tb = b.checked_at ? new Date(b.checked_at).getTime() : 0
          return ta - tb
        },
        render: (v: any) => v ? formatDateTime(v) : '-',
      },
      { title: '标记人', dataIndex: 'checked_by', width: 100, ...stringCol('checked_by', 100) },
      { title: '备注', dataIndex: 'remark', width: 160, ellipsis: true, ...stringCol('remark', 160) },
      {
        title: '操作', key: 'op', width: 200, fixed: 'right' as const,
        render: (_: any, r: StockCheckItem) => {
          const usageTotal = r.material_id ? orderUsageCache[r.material_id]?.total : undefined
          return (
            <Space size="small">
              <Button type="link" size="small" icon={<SaveOutlined />}
                disabled={readonly}
                onClick={() => saveItem(r)}>保存</Button>
              <Tooltip title="查看该物料被哪些盘点单盘点过">
                <Button
                  type="link" size="small" icon={<HistoryOutlined />}
                  onClick={() => openMaterialHistory(r)}
                />
              </Tooltip>
              {r.material_id != null && (
                <Tooltip title="查看使用该物料的订单及需求数">
                  <Button
                    type="link" size="small" icon={<UnorderedListOutlined />}
                    onClick={() => openUsageModal(r)}
                  >
                    使用订单{usageTotal != null ? ` ${usageTotal}单` : ''}
                  </Button>
                </Tooltip>
              )}
            </Space>
          )
        },
      },
    ]
  }, [items, readonly, saveItem, updateItem, openMaterialHistory, orderUsageCache, openUsageModal])

  const renderSearch = () => (
    <div className="card-modern" style={{ padding: 16, marginBottom: 16 }}>
      <Space wrap>
        <span data-tour="stock-check-search">
          <Input
            placeholder="输入订单号 (如 HJ2024-001)"
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            onPressEnter={handleSearch}
            allowClear
            style={{ width: 280 }}
            prefix={<SearchOutlined />}
          />
        </span>
        <Button type="primary" onClick={handleSearch}>搜索订单</Button>
        <Button onClick={() => {
          setSearchText('')
          setOrderNo('')
          setCheckIdParam(null)
          setActiveCheck(null)
          setItems([])
          setParams({})
        }}>清空</Button>
        {orderNo && !activeCheck && (
          <span data-tour="stock-check-create">
            <Button type="primary" ghost onClick={() => handleCreate(orderNo)} loading={loading}>
              为 {orderNo} 创建盘点单
            </Button>
          </span>
        )}
        <span data-tour="stock-check-manual-create">
          <span data-tour="stock-check-pool-badge">
            <Badge count={poolCount} size="small" offset={[10, -2]} overflowCount={999}>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setPickerOpen(true)}>
                手动盘点 — 选择物料
              </Button>
            </Badge>
          </span>
        </span>
        <Popover
          trigger="click"
          placement="bottomRight"
          content={
            <div style={{ width: 200 }}>
              <div style={{ marginBottom: 8, fontWeight: 500 }}>新手指引</div>
              <Button type="link" size="small" onClick={handleHelpClick} style={{ padding: 0, marginBottom: 8 }}>
                ▶ 立即查看
              </Button>
              <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 8 }}>
                <Checkbox checked={newbieMode} onChange={e => handleNewbieToggle(e.target.checked)}>
                  开启新手指引
                </Checkbox>
              </div>
            </div>
          }
        >
          <Button icon={<QuestionCircleOutlined />} shape="circle" title="新手指引" />
        </Popover>
      </Space>
    </div>
  )

  return (
    <div>
      {renderSearch()}
      {!activeCheck ? (
        <div className="card-modern" style={{ padding: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
            <Space>
              <h3 style={{ margin: 0 }}>最近盘点单</h3>
              <span data-tour="stock-check-type-filter">
                <Segmented
                  value={checkTypeFilter}
                  onChange={(v) => setCheckTypeFilter(v as string)}
                  options={[
                    { label: '全部', value: 'all' },
                    { label: '订单盘点', value: 'order' },
                    { label: '手动盘点', value: 'manual' },
                  ]}
                />
              </span>
            </Space>
            <Space wrap>
              {recentSearchInput}
              <DatePicker.RangePicker
                onChange={(d) => {
                  setDateRange([
                    d?.[0]?.format('YYYY-MM-DD'),
                    d?.[1]?.format('YYYY-MM-DD'),
                  ])
                }}
              />
              <Button icon={<ReloadOutlined />} onClick={reloadRecentList}>刷新</Button>
            </Space>
          </div>
          <Table
            rowKey="id"
            dataSource={recentTableProps.dataSource}
            loading={recentTableProps.loading}
            pagination={recentTableProps.pagination}
            onChange={recentTableProps.onChange}
            scroll={{ x: 1500 }}
            columns={[
              { title: '盘点单号', dataIndex: 'check_no', width: 180, sorter: true },
              {
                title: '类型', dataIndex: 'check_type', width: 90,
                render: (v: any) => v === 'manual'
                  ? <Tag color="purple">手动</Tag>
                  : <Tag color="blue">订单</Tag>,
              },
              { title: '订单号', dataIndex: 'order_no', width: 180, sorter: true, render: (v: any) => v || '—' },
              { title: '标题', dataIndex: 'title', ellipsis: true },
              {
                title: '状态', dataIndex: 'status', width: 100,
                filters: STATUS_OPTIONS,
                filteredValue: (recentFilters.status as string[] | undefined) ?? null,
                filterMultiple: true,
                render: (v: any) => <Tag color={STATUS_MAP[v]?.color || 'default'}>{STATUS_MAP[v]?.label || v}</Tag>,
              },
              { title: '盘点日期', dataIndex: 'check_date', width: 120, sorter: true },
              { title: '应盘', dataIndex: 'total_materials', width: 70, align: 'right' as const, sorter: true },
              { title: '已盘', dataIndex: 'checked_materials', width: 70, align: 'right' as const, sorter: true },
              {
                title: '总差异', dataIndex: 'total_diff_qty', width: 100, align: 'right' as const, sorter: true,
                render: (v: any) => v != null ? Number(v).toFixed(2) : '-',
              },
              { title: '创建人', dataIndex: 'created_by', width: 100 },
              { title: '创建时间', dataIndex: 'created_at', width: 160, sorter: true, render: (v: any) => v ? formatDateTime(v) : '-' },
              {
                title: '操作', key: 'op', width: 100, fixed: 'right' as const,
                render: (_: any, r: StockCheck) => (
                  <Button type="link" size="small" onClick={() => {
                    setCheckIdParam(r.id)
                    setOrderNo('')
                    setParams({ checkId: String(r.id) })
                    loadCheck(r.id)
                  }}>详情</Button>
                ),
              },
            ]}
          />
        </div>
      ) : (
        <div>
          <div className="card-modern" style={{ padding: 16, marginBottom: 16 }}>
            <Space style={{ marginBottom: 12 }} wrap>
              <Button icon={<ArrowLeftOutlined />} onClick={goBack}>返回</Button>
              <h2 style={{ margin: 0 }}>{activeCheck.check_no}</h2>
              <Tag color={STATUS_MAP[activeCheck.status || '']?.color || 'default'}>
                {STATUS_MAP[activeCheck.status || '']?.label || activeCheck.status}
              </Tag>
              {activeCheck.check_type === 'manual'
                ? <Tag color="purple">手动盘点</Tag>
                : <Tag color="blue">订单盘点</Tag>}
              {activeCheck.order_no
                ? <span style={{ color: '#64748b' }}>订单: {activeCheck.order_no}</span>
                : <span style={{ color: '#94a3b8' }}>订单: —</span>}
              <span style={{ color: '#64748b' }}>创建: {activeCheck.created_by} / {formatDateTime(activeCheck.created_at)}</span>
            </Space>
            <Row gutter={12}>
              <Col span={4}><Card size="small" className="card-modern">
                <div style={{ color: '#64748b', fontSize: 12 }}>应盘</div>
                <div style={{ fontSize: 22, fontWeight: 600 }}>{activeCheck.total_materials || 0}</div>
              </Card></Col>
              <Col span={4}><Card size="small" className="card-modern">
                <div style={{ color: '#64748b', fontSize: 12 }}>已盘</div>
                <div style={{ fontSize: 22, fontWeight: 600, color: '#16a34a' }}>{activeCheck.checked_materials || 0}</div>
              </Card></Col>
              <Col span={4}><Card size="small" className="card-modern">
                <div style={{ color: '#64748b', fontSize: 12 }}>未盘</div>
                <div style={{ fontSize: 22, fontWeight: 600, color: '#dc2626' }}>
                  {(activeCheck.total_materials || 0) - (activeCheck.checked_materials || 0)}
                </div>
              </Card></Col>
              <Col span={6}><Card size="small" className="card-modern">
                <div style={{ color: '#64748b', fontSize: 12 }}>总差异 (实盘-库存)</div>
                <div style={{ fontSize: 22, fontWeight: 600 }}>
                  {activeCheck.total_diff_qty != null ? Number(activeCheck.total_diff_qty).toFixed(2) : '0.00'}
                </div>
              </Card></Col>
              <Col span={6} style={{ textAlign: 'right' }} data-tour="stock-check-actions">
                <Space wrap>
                  <Button icon={<SaveOutlined />} onClick={saveAll} loading={savingAll} disabled={readonly}>
                    保存全部
                  </Button>
                  <Button type="primary" icon={<CheckCircleOutlined />} onClick={handleComplete} disabled={readonly}>
                    标记完成
                  </Button>
                  <Button danger icon={<StopOutlined />} onClick={handleCancel} disabled={readonly}>
                    取消
                  </Button>
                </Space>
              </Col>
            </Row>
          </div>
          <div className="card-modern" style={{ padding: 4 }} data-tour="stock-check-table">
            <Spin spinning={loading}>
              <Table
                rowKey="id"
                dataSource={items}
                columns={columns}
                pagination={{ pageSize: 50, showSizeChanger: true, showTotal: t => `共 ${t} 项` }}
                scroll={{ x: 1600, y: 600 }}
                size="small"
              />
            </Spin>
          </div>
        </div>
      )}
      <Tour
        open={tourOpen}
        steps={tourSteps}
        onClose={handleTourClose}
        onFinish={handleTourClose}
      />
      <Drawer
        title={historyMaterial ? `物料 ${historyMaterial.material_code} 历史盘点记录` : '历史盘点记录'}
        open={historyDrawerOpen}
        onClose={() => setHistoryDrawerOpen(false)}
        width={760}
      >
        {historyLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : historyItems.length === 0 ? (
          <Empty description="暂无历史盘点记录" />
        ) : (
          <Table
            rowKey="check_no"
            dataSource={historyItems}
            pagination={false}
            size="small"
            columns={[
              { title: '盘点单号', dataIndex: 'check_no', width: 160 },
              { title: '订单号', dataIndex: 'order_no', width: 160 },
              { title: '客户', dataIndex: 'customer', width: 140, ellipsis: true,
                render: (v: any) => v || '-' },
              { title: '状态', dataIndex: 'status', width: 90,
                render: (v: any) => <Tag color={STATUS_MAP[v]?.color || 'default'}>{STATUS_MAP[v]?.label || v}</Tag> },
              { title: '实盘数', dataIndex: 'actual_qty', width: 100, align: 'right' as const,
                render: (v: any) => v != null ? Number(v).toFixed(2) : '-' },
              { title: '完结时间', dataIndex: 'completed_at', width: 160,
                render: (v: any) => v ? formatDateTime(v) : '-' },
            ]}
            scroll={{ x: 1000 }}
          />
        )}
      </Drawer>
      <Modal
        title={
          usageMaterial
            ? `使用订单 — ${usageMaterial.material_code || ''} ${usageMaterial.material_name || ''}`.trim()
            : '使用订单'
        }
        open={usageModalOpen}
        onCancel={closeUsageModal}
        footer={null}
        width={1100}
        destroyOnClose
      >
        {(() => {
          const mid = usageMaterial?.material_id
          if (mid == null) return <Empty description="该物料无 ID" />
          const cache = orderUsageCache[mid]
          const pg = orderUsagePage[mid] || { page: 1, page_size: 10, keyword: '' }
          const data = cache?.items || []
          return (
            <div>
              <Space style={{ marginBottom: 12 }} wrap>
                <Tag color="blue">规格: {usageMaterial?.spec_model || '-'}</Tag>
                <Tag color="cyan">单位: {usageMaterial?.unit || '-'}</Tag>
                <Input.Search
                  placeholder="搜索订单号/客户"
                  allowClear
                  style={{ width: 240 }}
                  defaultValue={pg.keyword}
                  onSearch={(v) => {
                    setOrderUsagePage(prev => ({ ...prev, [mid]: { page: 1, page_size: 10, keyword: v } }))
                    fetchOrderUsage(mid, 1, v)
                  }}
                />
                <span style={{ color: '#64748b' }}>共 {cache?.total ?? 0} 个未结订单 (按需求数从高到低)</span>
              </Space>
              <Spin spinning={!!cache?.loading}>
                <Table
                  rowKey={(r: MaterialOrderUsage) => `${r.order_no}-${r.line_no}`}
                  dataSource={data}
                  size="small"
                  pagination={{
                    current: pg.page,
                    pageSize: pg.page_size,
                    total: cache?.total || 0,
                    showSizeChanger: false,
                    showTotal: t => `共 ${t} 条`,
                    onChange: (p) => {
                      setOrderUsagePage(prev => ({ ...prev, [mid]: { ...prev[mid], page: p } }))
                      fetchOrderUsage(mid, p, pg.keyword)
                    },
                  }}
                  columns={[
                    {
                      title: '订单号', dataIndex: 'order_no', width: 180,
                      render: (v: any, r: MaterialOrderUsage) => (
                        <a onClick={() => { closeUsageModal(); navigate(`/order-list?orderNo=${r.order_no}`) }}>{v}</a>
                      ),
                    },
                    { title: '行号', dataIndex: 'line_no', width: 70 },
                    { title: '客户', dataIndex: 'customer', width: 160, ellipsis: true,
                      render: (v: any) => v || '-' },
                    { title: '产品编码', dataIndex: 'product_code', width: 130, ellipsis: true,
                      render: (v: any) => v || '-' },
                    { title: '产品名称', dataIndex: 'product_name', width: 200, ellipsis: true,
                      render: (v: any) => v || '-' },
                    { title: 'BOM编号', dataIndex: 'bom_no', width: 130, ellipsis: true,
                      render: (v: any) => v || '-' },
                    {
                      title: '订单数量', dataIndex: 'order_qty', width: 100, align: 'right' as const,
                      render: (v: any) => v != null ? Number(v).toFixed(2) : '-',
                    },
                    {
                      title: '单台用量', dataIndex: 'standard_qty', width: 100, align: 'right' as const,
                      render: (v: any) => v != null ? Number(v).toFixed(4) : '-',
                    },
                    {
                      title: <strong>需求数</strong>, dataIndex: 'req_qty', width: 110, align: 'right' as const,
                      render: (v: any) => v != null
                        ? <strong style={{ color: '#1677ff' }}>{Number(v).toFixed(2)}</strong>
                        : '-',
                    },
                    { title: '交期', dataIndex: 'promised_date', width: 120,
                      render: (v: any) => v || '-' },
                    { title: '状态', dataIndex: 'status', width: 90,
                      render: (v: any) => v ? <Tag>{v}</Tag> : '-' },
                    { title: '订单性质', dataIndex: 'order_nature', width: 100, ellipsis: true,
                      render: (v: any) => v || '-' },
                  ]}
                  scroll={{ x: 1400 }}
                />
              </Spin>
            </div>
          )
        })()}
      </Modal>
      <MaterialPickerModal
        open={pickerOpen}
        onCancel={() => setPickerOpen(false)}
        onConfirm={handleCreateFromMaterials}
        confirmLoading={creating}
      />
    </div>
  )
}
