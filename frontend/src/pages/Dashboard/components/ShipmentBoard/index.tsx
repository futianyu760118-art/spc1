import { useState, useEffect, useCallback, useMemo } from 'react'
import { Button, Spin, Tooltip, message, Popover, Empty, Select, Row, Col } from 'antd'
import {
  ReloadOutlined,
  SyncOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
  QuestionCircleOutlined,
  WarningOutlined,
  RocketOutlined,
  BarChartOutlined,
  VerticalLeftOutlined,
  VerticalRightOutlined,
} from '@ant-design/icons'
import { Pie, Column } from '@ant-design/charts'
import { dashboardApi } from '@/services/api'
import dayjs from 'dayjs'

interface ShipmentItem {
  id: number
  order_no: string | null
  line_no: string | null
  shipping_plan: string | null
  is_overdue: boolean
  overdue_days: number
  customer: string | null
  customer_code: string | null
  product_code: string | null
  product_name: string | null
  order_qty: number | null
  completed_qty: number | null
  promised_date: string | null
  risk_level: string | null
  owner: string | null
  shipping_status_desc: string | null
  status: string | null
}

interface ShipmentData {
  items: ShipmentItem[]
  last_updated: string
}

const REFRESH_INTERVAL = 60000
const COLLAPSE_STORAGE_KEY = 'spc-shipment-board-collapse'

const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六']

const ShipmentBoard: React.FC = () => {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<ShipmentData | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [refreshingAt, setRefreshingAt] = useState<Date>(new Date())
  const [fullscreen, setFullscreen] = useState(false)
  const [ownerFilter, setOwnerFilter] = useState<string[]>([])
  const [showCharts, setShowCharts] = useState(false)
  const [collapsed, setCollapsed] = useState<{ danger: boolean; normal: boolean }>(() => {
    try {
      const raw = localStorage.getItem(COLLAPSE_STORAGE_KEY)
      if (raw) {
        const parsed = JSON.parse(raw)
        if (parsed && typeof parsed === 'object') {
          return { danger: !!parsed.danger, normal: !!parsed.normal }
        }
      }
    } catch {}
    return { danger: false, normal: false }
  })

  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSE_STORAGE_KEY, JSON.stringify(collapsed))
    } catch {}
  }, [collapsed])

  const toggleCollapse = useCallback((key: 'danger' | 'normal') => {
    setCollapsed(prev => ({ ...prev, [key]: !prev[key] }))
  }, [])

  const fetchData = useCallback(async () => {
    try {
      const res: any = await dashboardApi.getShipmentBoard()
      if (res?.code === 0) {
        setData(res.data)
        setRefreshingAt(new Date())
      }
    } catch (err) {
      console.error('Failed to fetch shipment board data:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  useEffect(() => {
    if (!autoRefresh) return
    const timer = setInterval(() => fetchData(), REFRESH_INTERVAL)
    return () => clearInterval(timer)
  }, [autoRefresh, fetchData])

  const handleManualRefresh = async () => {
    setLoading(true)
    await fetchData()
    message.success('数据已刷新')
  }

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && fullscreen) setFullscreen(false)
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [fullscreen])

  useEffect(() => {
    if (fullscreen) {
      const prev = document.body.style.overflow
      document.body.style.overflow = 'hidden'
      return () => { document.body.style.overflow = prev }
    }
  }, [fullscreen])

  const allItems = data?.items || []

  const ownerOptions = useMemo(() => {
    const set = new Map<string, number>()
    allItems.forEach(i => {
      const name = (i.owner || '').trim()
      if (name) set.set(name, (set.get(name) || 0) + 1)
    })
    return Array.from(set.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([name, count]) => ({ label: `${name} (${count})`, value: name }))
  }, [allItems])

  const rawItems = useMemo(() => {
    if (ownerFilter.length === 0) return allItems
    return allItems.filter(i => {
      const name = (i.owner || '').trim()
      return ownerFilter.includes(name)
    })
  }, [allItems, ownerFilter])

  const overdueItems = useMemo(() => {
    return rawItems
      .filter(i => i.is_overdue)
      .sort((a, b) => (b.overdue_days || 0) - (a.overdue_days || 0))
  }, [rawItems])

  const todayItems = useMemo(() => {
    const todayStr = dayjs().format('YYYY-MM-DD')
    return rawItems
      .filter(i => !i.is_overdue)
      .filter(i => i.shipping_plan && dayjs(i.shipping_plan).format('YYYY-MM-DD') === todayStr)
      .sort((a, b) => (a.order_no || '').localeCompare(b.order_no || ''))
  }, [rawItems])

  const statusPie = useMemo(() => {
    const buckets: Record<string, { name: string; value: number; color: string }> = {
      overdue: { name: '已逾期', value: 0, color: '#e11d48' },
      today: { name: '今日出货', value: 0, color: '#6366f1' },
    }
    rawItems.forEach(i => {
      if (i.is_overdue) buckets.overdue.value++
      else buckets.today.value++
    })
    return Object.values(buckets).filter(b => b.value > 0)
  }, [rawItems])

  const ownerBar = useMemo(() => {
    const map = new Map<string, number>()
    rawItems.forEach(i => {
      const name = (i.owner || '未指派').trim()
      map.set(name, (map.get(name) || 0) + 1)
    })
    return Array.from(map.entries())
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 12)
  }, [rawItems])

  const riskPie = useMemo(() => {
    const map: Record<string, { name: string; value: number; color: string }> = {
      red: { name: '高风险', value: 0, color: '#e11d48' },
      yellow: { name: '中风险', value: 0, color: '#d97706' },
      green: { name: '低风险', value: 0, color: '#059669' },
      none: { name: '未评估', value: 0, color: '#94a3b8' },
    }
    rawItems.forEach(i => {
      const lv = i.risk_level
      if (lv === 'red') map.red.value++
      else if (lv === 'yellow') map.yellow.value++
      else if (lv === 'green') map.green.value++
      else map.none.value++
    })
    return Object.values(map).filter(b => b.value > 0)
  }, [rawItems])

  if (loading && !data) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 0' }}>
        <Spin size="large" tip="加载出货计划看板..." />
      </div>
    )
  }

  if (!data) return null

  const renderCard = (item: ShipmentItem) => {
    const completed = item.completed_qty ?? 0
    const ordered = item.order_qty ?? 0
    const pct = ordered > 0 ? Math.min(100, Math.round((completed / ordered) * 100)) : 0
    const barClass = pct >= 100
      ? 'pb-progress-fill is-ready'
      : pct > 0 ? 'pb-progress-fill is-partial' : 'pb-progress-fill is-empty'

    let badge: React.ReactNode = null
    let cardAccent = ''
    if (item.is_overdue) {
      cardAccent = 'pb-card-overdue'
      badge = <span className="pb-badge pb-badge-danger">逾期 {item.overdue_days}天</span>
    } else if (item.risk_level === 'red') {
      cardAccent = 'pb-card-shortage'
      badge = <span className="pb-badge pb-badge-warning">高风险</span>
    } else if (item.risk_level === 'yellow') {
      cardAccent = 'pb-card-tomorrow'
      badge = <span className="pb-badge pb-badge-info">中风险</span>
    } else {
      cardAccent = 'pb-card-today'
      badge = <span className="pb-badge pb-badge-success">今日</span>
    }

    const dateLabel = item.shipping_plan ? dayjs(item.shipping_plan).format('MM-DD') : null
    const docNo = [item.order_no, item.line_no].filter(Boolean).join('/') || '-'
    const promisedEarly = item.promised_date && item.shipping_plan
      && dayjs(item.promised_date).isBefore(dayjs(item.shipping_plan), 'day')

    const cardBody = (
      <div className={`pb-card ${cardAccent}`}>
        <div className="pb-card-top">
          <span className="pb-card-date">{dateLabel || <span className="pb-text-muted">-</span>}</span>
          <span className="pb-card-doc pb-mono">{docNo}</span>
          {badge}
        </div>
        <div className="pb-card-mat">
          <div className="pb-fw600">客户：{item.customer || <span className="pb-text-muted">-</span>}</div>
          {(item.product_name || item.product_code) && (
            <div className="pb-text-xs pb-text-muted pb-ellipsis">
              {[item.product_code, item.product_name].filter(Boolean).join(' | ')}
            </div>
          )}
        </div>
        <div className="pb-card-numbers">
          <div className="pb-num"><span className="pb-num-label">完成</span><span className={`pb-mono pb-fw600 ${pct >= 100 ? 'pb-text-success' : ''}`}>{ordered > 0 ? `${completed.toLocaleString()}/${ordered.toLocaleString()}` : '-'}</span></div>
          {item.shipping_plan && (
            <div className="pb-num"><span className="pb-num-label">出货计划</span><span className="pb-mono pb-fw600">{dayjs(item.shipping_plan).format('YYYY-MM-DD')}</span></div>
          )}
          {item.promised_date && (
            <div className="pb-num pb-num-owner"><span className="pb-num-label">交期</span><span className={`pb-mono ${promisedEarly ? 'pb-text-danger' : ''}`}>{dayjs(item.promised_date).format('MM-DD')}</span></div>
          )}
        </div>
        {ordered > 0 && (
          <div className="pb-progress-track">
            <div className={barClass} style={{ width: `${pct}%` }} />
          </div>
        )}
        {item.shipping_status_desc && (
          <div className="pb-text-xs pb-text-muted pb-ellipsis" title={item.shipping_status_desc}>{item.shipping_status_desc}</div>
        )}
      </div>
    )

    return item.shipping_status_desc ? (
      <Tooltip key={item.id} title={item.shipping_status_desc} placement="top">{cardBody}</Tooltip>
    ) : (
      <div key={item.id}>{cardBody}</div>
    )
  }

  const todayDateLabel = dayjs().format('MM-DD')
  const todayWeekday = `星期${WEEKDAYS[dayjs().day()]}`

  const headerContent = (
    <div className={`pb-header card-modern ${fullscreen ? 'pb-header-fs' : ''}`}>
      <div className="pb-header-left">
        <Select
          mode="multiple"
          allowClear
          maxTagCount="responsive"
          placeholder="筛选业务员"
          value={ownerFilter}
          onChange={setOwnerFilter}
          options={ownerOptions}
          style={{ minWidth: 180, maxWidth: 360 }}
        />
      </div>
      <div className="pb-header-right">
        <Popover
          title="出货计划看板说明"
          content={
            <div style={{ maxWidth: 360, lineHeight: 1.8, fontSize: 13 }}>
              <p><b>数据范围：</b>展示所有有"出货计划"日期、且<b>未发货完成</b>（发货完成日期为空）、订单未关闭的销售订单。</p>
              <p><b>分组：</b></p>
              <ul style={{ paddingLeft: 16, margin: '4px 0' }}>
                <li>左列「已逾期」— 出货计划日期早于今天的订单，按逾期天数降序。</li>
                <li>右列「今日出货」— 出货计划日期为今天的订单。</li>
              </ul>
              <p><b>卡片颜色：</b></p>
              <ul style={{ paddingLeft: 16, margin: '4px 0' }}>
                <li><span style={{ color: '#e11d48' }}>■</span> 红色顶条 — 已逾期</li>
                <li><span style={{ color: '#d97706' }}>■</span> 橙色顶条 — 今日出货且高风险</li>
                <li><span style={{ color: '#0ea5e9' }}>■</span> 蓝色顶条 — 今日出货且中风险</li>
                <li><span style={{ color: '#d4380d' }}>■</span> 橙红顶条 — 今日出货</li>
              </ul>
              <p><b>交期：</b>红色交期日期表示客户交期早于出货计划，交付紧张。</p>
              <p><b>自动刷新：</b>每60秒自动刷新，可点击同步图标切换手动模式。</p>
            </div>
          }
          trigger="click"
        >
          <Button icon={<QuestionCircleOutlined />} type="text" size="small" />
        </Popover>
        <span className="pb-time">{refreshingAt.toLocaleTimeString('zh-CN', { hour12: false })}</span>
        {!fullscreen && (
          <>
            <Tooltip title="刷新">
              <Button icon={<ReloadOutlined />} onClick={handleManualRefresh} loading={loading} size="small" type="text" />
            </Tooltip>
            <Tooltip title={autoRefresh ? '自动刷新(60s)' : '手动刷新'}>
              <Button icon={<SyncOutlined spin={autoRefresh} />} type="text" size="small" onClick={() => setAutoRefresh(!autoRefresh)} className={autoRefresh ? 'is-active' : ''} />
            </Tooltip>
          </>
        )}
        <Tooltip title={fullscreen ? '退出全屏 (ESC)' : '全屏'}>
          <Button icon={fullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />} type="text" size="small" onClick={() => setFullscreen(!fullscreen)} />
        </Tooltip>
        <Tooltip title={showCharts ? '隐藏图表' : '显示图表'}>
          <Button icon={<BarChartOutlined />} type="text" size="small" onClick={() => setShowCharts(!showCharts)} className={showCharts ? 'is-active' : ''} />
        </Tooltip>
      </div>
    </div>
  )

  const chartsContent = showCharts && (
    <Row gutter={[14, 14]} style={{ marginBottom: 14 }}>
      <Col xs={24} md={8}>
        <div className="card-modern" style={{ padding: '16px 20px', height: '100%' }}>
          <h3 className="text-sm font-semibold m-0 mb-3" style={{ color: '#475569' }}>状态分布</h3>
          {statusPie.length > 0 ? (
            <Pie
              data={statusPie}
              angleField="value"
              colorField="name"
              radius={0.85}
              innerRadius={0.55}
              color={statusPie.map(d => d.color)}
              label={{ text: (d: any) => `${d.name}\n${d.value}`, style: { fontSize: 11, fontWeight: 500 } }}
              legend={{ color: { position: 'bottom' as const, layout: { justifyContent: 'center' } } }}
              statistic={{
                title: { content: '总数', style: { fontSize: '12px', color: '#94a3b8' } },
                content: { content: String(statusPie.reduce((s, d) => s + d.value, 0)), style: { fontSize: '22px', fontWeight: 700, color: '#1e293b' } },
              }}
              interaction={{ elementHighlight: true }}
              height={240}
            />
          ) : (
            <div style={{ height: 240, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>暂无数据</div>
          )}
        </div>
      </Col>
      <Col xs={24} md={8}>
        <div className="card-modern" style={{ padding: '16px 20px', height: '100%' }}>
          <h3 className="text-sm font-semibold m-0 mb-3" style={{ color: '#475569' }}>业务员分布</h3>
          {ownerBar.length > 0 ? (
            <Column
              data={ownerBar}
              xField="name"
              yField="value"
              color="#6366f1"
              columnStyle={{ radius: [4, 4, 0, 0] }}
              label={{ text: 'value', position: 'inside' as const, style: { fill: '#fff', fontSize: 11, fontWeight: 600 } }}
              axis={{
                x: { title: false, label: { style: { fontSize: 11 }, autoRotate: true } },
                y: { title: false, label: { style: { fontSize: 11 } } },
              }}
              height={240}
            />
          ) : (
            <div style={{ height: 240, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>暂无数据</div>
          )}
        </div>
      </Col>
      <Col xs={24} md={8}>
        <div className="card-modern" style={{ padding: '16px 20px', height: '100%' }}>
          <h3 className="text-sm font-semibold m-0 mb-3" style={{ color: '#475569' }}>风险等级分布</h3>
          {riskPie.length > 0 ? (
            <Pie
              data={riskPie}
              angleField="value"
              colorField="name"
              radius={0.85}
              innerRadius={0.55}
              color={riskPie.map(d => d.color)}
              label={{ text: (d: any) => `${d.name}\n${d.value}`, style: { fontSize: 11, fontWeight: 500 } }}
              legend={{ color: { position: 'bottom' as const, layout: { justifyContent: 'center' } } }}
              statistic={{
                title: { content: '风险订单', style: { fontSize: '12px', color: '#94a3b8' } },
                content: { content: String(riskPie.filter(d => d.name !== '未评估').reduce((s, d) => s + d.value, 0)), style: { fontSize: '22px', fontWeight: 700, color: '#1e293b' } },
              }}
              interaction={{ elementHighlight: true }}
              height={240}
            />
          ) : (
            <div style={{ height: 240, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>暂无数据</div>
          )}
        </div>
      </Col>
    </Row>
  )

  const renderPanel = (
    title: React.ReactNode,
    count: number,
    accent: 'danger' | 'normal',
    dataSource: ShipmentItem[],
    bodyHeight: string,
    emptyText: string,
    isCollapsed: boolean,
    onToggleCollapse: () => void,
  ) => {
    const ToggleIcon = accent === 'danger'
      ? (isCollapsed ? VerticalRightOutlined : VerticalLeftOutlined)
      : (isCollapsed ? VerticalLeftOutlined : VerticalRightOutlined)
    return (
      <div className={`pb-panel pb-panel-${accent} ${isCollapsed ? 'is-collapsed' : ''}`}>
        <div className={`pb-panel-head pb-panel-head-${accent}`}>
          <span className="pb-panel-title">{title}</span>
          <span className="pb-panel-count">{count}</span>
          <Tooltip title={isCollapsed ? '展开' : '收起'}>
            <Button type="text" size="small" icon={<ToggleIcon />} onClick={onToggleCollapse} className="pb-panel-toggle" />
          </Tooltip>
        </div>
        <div className="pb-panel-body" style={{ height: bodyHeight }}>
          {dataSource.length > 0 ? (
            <div className="pb-card-grid">{dataSource.map(renderCard)}</div>
          ) : (
            <div style={{ padding: '32px 0' }}>
              <Empty description={emptyText} image={Empty.PRESENTED_IMAGE_SIMPLE} />
            </div>
          )}
        </div>
      </div>
    )
  }

  const css = `
    .pb-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 20px; margin-bottom: 14px; gap: 12px; }
    .pb-header-fs { margin-bottom: 1em; }
    .pb-header-left { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; flex: 1; min-width: 0; }
    .pb-header-right { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
    .pb-time { color: var(--text-muted); font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace; font-size: calc(0.8rem * var(--font-size-scale)); font-variant-numeric: tabular-nums; padding: 0 8px; }
    .pb-header .ant-btn-text { width: 32px; height: 32px; padding: 0; border-radius: 10px; color: var(--text-secondary); background: transparent; transition: all .18s ease; }
    .pb-header .ant-btn-text:hover { background: rgba(99, 102, 241, 0.10); color: #4f46e5; }
    .pb-header .ant-btn-text.is-active { background: rgba(99, 102, 241, 0.14); color: #4f46e5; }
    .pb-mono { font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace; font-variant-numeric: tabular-nums; }
    .pb-fw600 { font-weight: 600; }
    .pb-text-danger { color: #e11d48; }
    .pb-text-success { color: #059669; }
    .pb-text-muted { color: var(--text-muted); }
    .pb-text-xs { font-size: 0.85em; }
    .pb-ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .pb-progress-track { width: 100%; height: 8px; background: rgba(99, 102, 241, 0.08); border-radius: 999px; overflow: hidden; }
    .pb-progress-fill { height: 100%; border-radius: 999px; transition: width .35s ease; background: linear-gradient(90deg, #6366f1, #818cf8); }
    .pb-progress-fill.is-ready { background: linear-gradient(90deg, #059669, #34d399); }
    .pb-progress-fill.is-partial { background: linear-gradient(90deg, #d97706, #fbbf24); }
    .pb-progress-fill.is-empty { background: rgba(99, 102, 241, 0.18); }
    .pb-split { display: flex; gap: 14px; align-items: stretch; }
    .pb-panel { flex: 1; min-width: 0; display: flex; flex-direction: column; border-radius: 16px; overflow: hidden; background: rgba(255, 255, 255, 0.72); backdrop-filter: blur(14px) saturate(1.4); -webkit-backdrop-filter: blur(14px) saturate(1.4); border: 1px solid rgba(226, 232, 240, 0.8); box-shadow: 0 4px 24px rgba(15, 23, 42, 0.05); position: relative; transition: flex-basis .3s cubic-bezier(.4, 0, .2, 1), width .3s cubic-bezier(.4, 0, .2, 1); }
    .pb-panel::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; border-radius: 16px 16px 0 0; }
    .pb-panel-danger::before { background: linear-gradient(90deg, #e11d48, #fb7185); }
    .pb-panel-normal::before { background: linear-gradient(90deg, #6366f1, #818cf8); }
    .pb-panel-head { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; color: var(--text-primary); font-weight: 600; font-size: calc(0.95rem * var(--font-size-scale)); border-bottom: 1px solid rgba(226, 232, 240, 0.6); }
    .pb-header-fs .pb-panel-head { font-size: calc(1.2rem * var(--font-size-scale)); padding: 16px 22px; }
    .pb-panel-title { display: flex; align-items: center; gap: 8px; }
    .pb-panel-title .anticon { font-size: 1.15em; }
    .pb-panel-danger .pb-panel-title .anticon { color: #e11d48; }
    .pb-panel-normal .pb-panel-title .anticon { color: #6366f1; }
    .pb-panel-count { background: rgba(99, 102, 241, 0.10); color: #4f46e5; padding: 2px 12px; border-radius: 999px; font-size: 0.88em; font-weight: 600; font-variant-numeric: tabular-nums; min-width: 28px; text-align: center; }
    .pb-panel-danger .pb-panel-count { background: rgba(225, 29, 72, 0.10); color: #be123c; }
    .pb-panel-body { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; background: linear-gradient(180deg, rgba(248, 250, 252, 0.5), rgba(241, 245, 249, 0.4)); }
    .pb-panel-body::-webkit-scrollbar { width: 8px; height: 8px; }
    .pb-panel-body::-webkit-scrollbar-track { background: transparent; }
    .pb-panel-body::-webkit-scrollbar-thumb { background: rgba(99, 102, 241, 0.20); border-radius: 999px; }
    .pb-panel-body::-webkit-scrollbar-thumb:hover { background: rgba(99, 102, 241, 0.35); }
    .pb-card-grid { display: flex; flex-direction: column; gap: 12px; padding: 14px; }
    .pb-header-fs .pb-card-grid { gap: 16px; padding: 18px; }
    .pb-card { position: relative; background: rgba(255, 255, 255, 0.82); backdrop-filter: blur(16px) saturate(1.4); -webkit-backdrop-filter: blur(16px) saturate(1.4); border-radius: 14px; padding: 16px 18px 14px; border: 1px solid rgba(226, 232, 240, 0.8); box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04); transition: transform .25s ease, box-shadow .25s ease, border-color .25s ease; display: flex; flex-direction: column; gap: 12px; font-size: calc(0.9375rem * var(--font-size-scale)); color: var(--text-primary); overflow: hidden; }
    .pb-header-fs .pb-card { font-size: calc(1.1875rem * var(--font-size-scale)); padding: 20px 22px 18px; }
    .pb-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: linear-gradient(90deg, #94a3b8, #cbd5e1); border-radius: 14px 14px 0 0; }
    .pb-card:hover { transform: translateY(-3px); box-shadow: 0 12px 32px rgba(15, 23, 42, 0.10); border-color: rgba(99, 102, 241, 0.25); }
    .pb-card-overdue::before { background: linear-gradient(90deg, #e11d48, #fb7185); }
    .pb-card-shortage::before { background: linear-gradient(90deg, #d97706, #fbbf24); }
    .pb-card-ready::before { background: linear-gradient(90deg, #059669, #34d399); }
    .pb-card-today::before { background: linear-gradient(90deg, #d4380d, #f97316); }
    .pb-card-tomorrow::before { background: linear-gradient(90deg, #0ea5e9, #38bdf8); }
    .pb-card-overdue:hover { box-shadow: 0 12px 32px rgba(225, 29, 72, 0.15); border-color: rgba(225, 29, 72, 0.30); }
    .pb-card-shortage:hover { box-shadow: 0 12px 32px rgba(217, 119, 6, 0.15); border-color: rgba(217, 119, 6, 0.30); }
    .pb-card-today:hover { box-shadow: 0 12px 32px rgba(212, 56, 13, 0.15); border-color: rgba(212, 56, 13, 0.30); }
    .pb-card-tomorrow:hover { box-shadow: 0 12px 32px rgba(14, 165, 233, 0.15); border-color: rgba(14, 165, 233, 0.30); }
    .pb-card-top { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .pb-card-date { font-weight: 700; font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace; font-size: 0.95em; font-variant-numeric: tabular-nums; background: rgba(99, 102, 241, 0.08); color: #4338ca; padding: 2px 8px; border-radius: 6px; }
    .pb-card-doc { font-size: 0.9em; color: var(--text-secondary); word-break: break-all; flex: 1; min-width: 0; font-weight: 500; }
    .pb-badge { font-size: 0.78em; padding: 3px 10px; border-radius: 999px; font-weight: 600; white-space: nowrap; letter-spacing: 0.2px; display: inline-flex; align-items: center; gap: 4px; line-height: 1.4; }
    .pb-badge-danger { background: #fee2e2; color: #b91c1c; }
    .pb-badge-warning { background: #fef3c7; color: #b45309; }
    .pb-badge-success { background: #d1fae5; color: #047857; }
    .pb-badge-today { background: #ffedd5; color: #c2410c; }
    .pb-badge-info { background: #dbeafe; color: #1d4ed8; }
    .pb-card-mat { line-height: 1.35; }
    .pb-card-mat .pb-text-xs { font-size: 0.88em; margin-top: 3px; }
    .pb-card-numbers { display: flex; align-items: baseline; gap: 18px; flex-wrap: wrap; font-size: 1em; padding-top: 10px; border-top: 1px dashed rgba(226, 232, 240, 0.7); }
    .pb-num { display: flex; align-items: baseline; gap: 5px; white-space: nowrap; }
    .pb-num-label { color: var(--text-muted); font-size: 0.78em; font-weight: 500; }
    .pb-num .pb-mono { font-size: 1.05em; font-weight: 600; color: var(--text-primary); }
    .pb-num-owner { margin-left: auto; }
    .pb-panel-toggle { width: 28px; height: 28px; padding: 0; border-radius: 8px; color: var(--text-secondary); background: transparent; transition: all .18s ease; flex-shrink: 0; }
    .pb-panel-toggle:hover { background: rgba(99, 102, 241, 0.10); color: #4f46e5; }
    .pb-panel-danger .pb-panel-toggle:hover { background: rgba(225, 29, 72, 0.10); color: #be123c; }
    .pb-panel.is-collapsed { flex: 0 0 60px; }
    .pb-panel.is-collapsed .pb-panel-body { display: none; }
    .pb-panel.is-collapsed .pb-panel-head { flex-direction: column; align-items: center; justify-content: flex-start; height: 100%; padding: 16px 6px 14px; border-bottom: none; gap: 14px; }
    .pb-panel.is-collapsed .pb-panel-title { writing-mode: vertical-rl; text-orientation: mixed; letter-spacing: 2px; flex: 1; display: flex; align-items: center; justify-content: center; font-size: 0.92em; min-height: 0; }
    .pb-panel.is-collapsed .pb-panel-title .anticon { font-size: 1.1em; }
    .pb-panel.is-collapsed .pb-panel-count { writing-mode: horizontal-tb; }
    .pb-panel.is-collapsed .pb-panel-toggle { order: -1; }
    @media (max-width: 1100px) {
      .pb-split { flex-direction: column; }
      .pb-panel.is-collapsed { flex: 0 0 auto; width: 100%; height: 48px; }
      .pb-panel.is-collapsed .pb-panel-head { flex-direction: row; height: 48px; padding: 0 14px; gap: 10px; justify-content: space-between; }
      .pb-panel.is-collapsed .pb-panel-title { writing-mode: horizontal-tb; flex: 1; }
      .pb-panel.is-collapsed .pb-panel-toggle { order: 0; }
    }
  `

  if (fullscreen) {
    return (
      <div className="pb-fullscreen pb-header-fs" style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 9999, background: '#fff', padding: '1.2em 1.5em', overflow: 'hidden', display: 'flex', flexDirection: 'column', fontSize: '1.15em' }}>
        <style>{css}</style>
        {headerContent}
        {chartsContent}
        <div className="pb-split" style={{ flex: 1, minHeight: 0 }}>
          {renderPanel(<span><WarningOutlined /> 已逾期</span>, overdueItems.length, 'danger', overdueItems, '100%', '暂无逾期项', collapsed.danger, () => toggleCollapse('danger'))}
          {renderPanel(<span><RocketOutlined /> 今日出货 · {todayDateLabel} {todayWeekday}</span>, todayItems.length, 'normal', todayItems, '100%', '今日暂无出货', collapsed.normal, () => toggleCollapse('normal'))}
        </div>
      </div>
    )
  }

  return (
    <div>
      <style>{css}</style>
      <div style={{ padding: '12px 16px' }}>
        {headerContent}
        {chartsContent}
        <div className="pb-split" style={{ minHeight: 420, maxHeight: 'calc(100vh - 18em)' }}>
          {renderPanel(<span><WarningOutlined /> 已逾期</span>, overdueItems.length, 'danger', overdueItems, 'calc(100vh - 22em)', '暂无逾期项', collapsed.danger, () => toggleCollapse('danger'))}
          {renderPanel(<span><RocketOutlined /> 今日出货 · {todayDateLabel} {todayWeekday}</span>, todayItems.length, 'normal', todayItems, 'calc(100vh - 22em)', '今日暂无出货', collapsed.normal, () => toggleCollapse('normal'))}
        </div>
      </div>
    </div>
  )
}

export default ShipmentBoard
