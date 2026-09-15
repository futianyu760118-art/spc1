import { useCallback, useEffect, useRef, useState } from 'react'
import { Tabs, Button } from 'antd'
import OverviewTab from './OverviewTab'
import StockCheckTab from './StockCheckTab'

type TabKey = 'overview' | 'stock_check'

const REFRESH_OVERVIEW = 30 * 60 * 1000  // 30 分钟
const REFRESH_CHECK = 5 * 60 * 1000      // 5 分钟

export default function InventoryBoard() {
  const [tab, setTab] = useState<TabKey>('overview')
  const [refreshKey, setRefreshKey] = useState(0)
  const [loading, setLoading] = useState(false)

  const handleRefresh = useCallback(() => {
    setRefreshKey((k) => k + 1)
  }, [])

  // 自动刷新
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current)
    const interval = tab === 'overview' ? REFRESH_OVERVIEW : REFRESH_CHECK
    timerRef.current = setInterval(() => setRefreshKey((k) => k + 1), interval)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [tab])

  return (
    <div>
      <div className="card mb12" style={{ padding: '8px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Tabs
          activeKey={tab}
          onChange={(k) => setTab(k as TabKey)}
          items={[
            { key: 'overview', label: '库存概览' },
            { key: 'stock_check', label: '盘点明细' },
          ]}
          style={{ flex: 1 }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {loading && <span style={{ fontSize: 12, color: '#94a3b8' }}>加载中…</span>}
          <Button size="small" onClick={handleRefresh}>刷新</Button>
        </div>
      </div>

      <div key={`${tab}-${refreshKey}`}>
        {tab === 'overview' ? (
          <OverviewTab onLoadingChange={setLoading} />
        ) : (
          <StockCheckTab onLoadingChange={setLoading} />
        )}
      </div>
    </div>
  )
}
