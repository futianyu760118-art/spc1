import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Table, Input, Button, Space, Tag, message, Modal, Card, Row, Col,
  InputNumber, Checkbox, Spin, Popover, Tour, DatePicker,
} from 'antd'
import { SearchOutlined, ReloadOutlined, CheckCircleOutlined, StopOutlined, ArrowLeftOutlined, SaveOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import { useAntTableQuery } from '@/hooks/useAntTableQuery'
import { materialApi } from '@/services/api'
import { formatDateTime } from '@/utils'
import { useUiPreferencesStore } from '@/store/uiPreferences'
import { stockCheckTourSteps, STOCK_CHECK_TOUR_ID } from './StockCheckTour'

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
  order_no: string
  title?: string | null
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

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  open: { label: '待盘点', color: 'default' },
  in_progress: { label: '进行中', color: 'processing' },
  completed: { label: '已完成', color: 'success' },
  cancelled: { label: '已取消', color: 'error' },
}

export default function StockCheckPage() {
  const [params, setParams] = useSearchParams()
  const [orderNo, setOrderNo] = useState<string>(params.get('orderNo') || '')
  const [searchText, setSearchText] = useState<string>('')

  const [activeCheck, setActiveCheck] = useState<StockCheck | null>(null)
  const [items, setItems] = useState<StockCheckItem[]>([])
  const [recent, setRecent] = useState<StockCheck[]>([])
  const [recentTotal, setRecentTotal] = useState(0)
  const [recentPage, setRecentPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [savingAll, setSavingAll] = useState(false)

  const loadRecent = useCallback(async (params: {
    page?: number
    page_size?: number
    keyword?: string
    sort_by?: string
    sort_order?: 'asc' | 'desc'
    status?: string[]
    date_from?: string
    date_to?: string
  } = {}) => {
    try {
      const { page: p = 1, page_size: ps = 20, ...rest } = params
      const query: any = { page: p, page_size: ps }
      if (rest.keyword) query.keyword = rest.keyword
      if (rest.status?.length) query.status = rest.status.join(',')
      if (rest.date_from) query.date_from = rest.date_from
      if (rest.date_to) query.date_to = rest.date_to
      if (rest.sort_by) query.sort_by = rest.sort_by
      if (rest.sort_order) query.sort_order = rest.sort_order
      const res: any = await materialApi.getRecentStockChecks(query)
      setRecent(res.data?.items || [])
      setRecentTotal(res.data?.total || 0)
      setRecentPage(p)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '加载最近盘点失败')
    }
  }, [])

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

  const handleCreate = useCallback(async (no: string) => {
    setLoading(true)
    try {
      const res: any = await materialApi.createStockCheckFromOrder(no, {})
      const c: StockCheck = res.data
      message.success(`已创建盘点单 ${c.check_no}`)
      setActiveCheck(c)
      setItems(c.items || [])
      await loadRecent({ page: 1 })
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '创建盘点单失败')
    } finally {
      setLoading(false)
    }
  }, [loadRecent])

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

  const STATUS_OPTIONS = [
    { text: '待盘点', value: 'open' },
    { text: '进行中', value: 'in_progress' },
    { text: '已完成', value: 'completed' },
    { text: '已取消', value: 'cancelled' },
  ]

  const {
    tableProps: recentTableProps,
    searchInput: recentSearchInput,
    keyword: recentKeyword,
  } = useAntTableQuery({
    fetchData: async (params) => {
      const res: any = await materialApi.getRecentStockChecks({
        page: params.page,
        page_size: params.page_size,
        keyword: params.keyword,
        sort_by: params.sort_by,
        sort_order: params.sort_order,
        status: (params.status as string[] | undefined)?.join(','),
        date_from: params.date_from,
        date_to: params.date_to,
      })
      return { items: res.data?.items || [], total: res.data?.total || 0 }
    },
    filterToQuery: (filters) => ({
      status: filters.status as string[] | undefined,
    }),
  })

  const [dateRange, setDateRange] = useState<[string?, string?]>([])

  const reloadRecent = useCallback(() => {
    setRecentPage(1)
    loadRecent({ page: 1, keyword: recentKeyword })
  }, [recentKeyword, loadRecent])

  useEffect(() => {
    if (orderNo && !activeCheck) {
      materialApi.getStockChecksByOrder(orderNo).then((res: any) => {
        const list: StockCheck[] = res.data || []
        const ongoing = list.find(c => c.status === 'in_progress' || c.status === 'open')
        if (ongoing) {
          loadCheck(ongoing.id)
        }
      }).catch(() => { /* silent */ })
    }
  }, [orderNo, activeCheck, loadCheck])

  useEffect(() => {
    if (!activeCheck) {
      // hook drives reload; nothing to do here
    }
  }, [activeCheck])

  const newbieMode = useUiPreferencesStore(s => s.preferences?.newbie_mode !== false)
  const seenTour = useUiPreferencesStore(s => s.preferences?.['tours_seen']?.[STOCK_CHECK_TOUR_ID])
  const setUiFlag = useUiPreferencesStore(s => s.setFlag)
  const [tourOpen, setTourOpen] = useState(false)

  useEffect(() => {
    if (!newbieMode) return
    if (seenTour) return
    const t = setTimeout(() => setTourOpen(true), 500)
    return () => clearTimeout(t)
  }, [newbieMode, seenTour])

  const handleTourClose = useCallback(() => {
    const current = useUiPreferencesStore.getState().getFlag('tours_seen', {}) as Record<string, boolean>
    useUiPreferencesStore.getState().setFlag('tours_seen', { ...current, [STOCK_CHECK_TOUR_ID]: true })
    setTourOpen(false)
  }, [])

  const handleHelpClick = useCallback(() => {
    setTourOpen(true)
  }, [])

  const handleNewbieToggle = useCallback((checked: boolean) => {
    setUiFlag('newbie_mode', checked)
  }, [setUiFlag])

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
  }, [activeCheck])

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
  }, [])

  const updateItem = useCallback((id: number, patch: Partial<StockCheckItem>) => {
    setItems(prev => prev.map(p => p.id === id ? { ...p, ...patch } : p))
  }, [])

  const readonly = activeCheck?.status === 'completed' || activeCheck?.status === 'cancelled'

  const columns = useMemo(() => [
    { title: '物料编码', dataIndex: 'material_code', width: 140, fixed: 'left' as const },
    { title: '物料名称', dataIndex: 'material_name', width: 200, ellipsis: true },
    { title: '规格', dataIndex: 'spec_model', width: 140, ellipsis: true },
    { title: '单位', dataIndex: 'unit', width: 60 },
    {
      title: '应盘数', dataIndex: 'req_qty', width: 90, align: 'right' as const,
      render: (v: any) => v != null ? Number(v).toFixed(2) : '-',
    },
    {
      title: '库存数', dataIndex: 'system_qty', width: 90, align: 'right' as const,
      render: (v: any) => v != null ? Number(v).toFixed(2) : '-',
    },
    {
      title: '盘点数', dataIndex: 'actual_qty', width: 120, align: 'right' as const,
      render: (_: any, r: StockCheckItem) => (
        <InputNumber
          size="small"
          min={0}
          step={0.01}
          style={{ width: 100 }}
          disabled={readonly}
          value={r.actual_qty != null ? Number(r.actual_qty) : null}
          onChange={(v) => updateItem(r.id, { actual_qty: v == null ? null : Number(v) })}
        />
      ),
    },
    {
      title: <span data-tour="stock-check-diff">差异</span>, dataIndex: 'diff_qty', width: 90, align: 'right' as const,
      render: (v: any) => {
        if (v == null) return '-'
        const n = Number(v)
        const color = n > 0 ? '#16a34a' : n < 0 ? '#dc2626' : '#64748b'
        return <span style={{ color, fontWeight: 500 }}>{n.toFixed(2)}</span>
      },
    },
    {
      title: '已盘', dataIndex: 'is_checked', width: 70, align: 'center' as const,
      render: (_: any, r: StockCheckItem) => (
        <Checkbox
          disabled={readonly}
          checked={r.is_checked === 1}
          onChange={(e) => updateItem(r.id, { is_checked: e.target.checked ? 1 : 0 })}
        />
      ),
    },
    { title: '标记时间', dataIndex: 'checked_at', width: 140, render: (v: any) => v ? formatDateTime(v) : '-' },
    { title: '标记人', dataIndex: 'checked_by', width: 100 },
    { title: '备注', dataIndex: 'remark', width: 160, ellipsis: true },
    {
      title: '操作', key: 'op', width: 80, fixed: 'right' as const,
      render: (_: any, r: StockCheckItem) => (
        <Button type="link" size="small" icon={<SaveOutlined />}
          disabled={readonly}
          onClick={() => saveItem(r)}>保存</Button>
      ),
    },
  ], [readonly, saveItem, updateItem])

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
        <Button onClick={() => { setSearchText(''); setOrderNo(''); setActiveCheck(null); setItems([]); setParams({}) }}>清空</Button>
        {orderNo && !activeCheck && (
          <span data-tour="stock-check-create">
            <Button type="primary" ghost onClick={() => handleCreate(orderNo)} loading={loading}>
              为 {orderNo} 创建盘点单
            </Button>
          </span>
        )}
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
            <h3 style={{ margin: 0 }}>最近盘点单</h3>
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
              <Button icon={<ReloadOutlined />} onClick={reloadRecent}>刷新</Button>
            </Space>
          </div>
          <Table
            rowKey="id"
            {...(recentTableProps as any)}
            scroll={{ x: 1400 }}
            columns={[
              { title: '盘点单号', dataIndex: 'check_no', width: 180, sorter: true },
              { title: '订单号', dataIndex: 'order_no', width: 180, sorter: true },
              { title: '标题', dataIndex: 'title', ellipsis: true },
              {
                title: '状态', dataIndex: 'status', width: 100,
                filters: STATUS_OPTIONS,
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
                  <Button type="link" size="small" onClick={() => loadCheck(r.id)}>详情</Button>
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
              <span style={{ color: '#64748b' }}>订单: {activeCheck.order_no}</span>
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
        steps={stockCheckTourSteps}
        onClose={handleTourClose}
        onFinish={handleTourClose}
      />
    </div>
  )
}
