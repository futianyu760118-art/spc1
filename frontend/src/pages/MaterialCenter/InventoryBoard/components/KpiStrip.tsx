import { Spin } from 'antd'

interface KpiItem {
  label: string
  value: string | number
  unit?: string
  tone?: 'default' | 'good' | 'bad' | 'warn'
}

interface Props {
  items: KpiItem[]
  loading?: boolean
}

function fmt(n: string | number): string {
  if (typeof n === 'string') return n
  if (n == null || Number.isNaN(n)) return '—'
  return n.toLocaleString()
}

export default function KpiStrip({ items, loading }: Props) {
  return (
    <Spin spinning={!!loading}>
      <div className="grid g4" style={{ gap: 12 }}>
        {items.map((it, i) => (
          <div key={i} className="card stat-card" style={{
            ['--accent' as any]: it.tone === 'good' ? 'var(--brand-500, #10b981)'
              : it.tone === 'bad' ? '#ef4444'
              : it.tone === 'warn' ? '#f59e0b'
              : 'var(--brand-500, #3b82f6)',
            ['--accent-bg' as any]: it.tone === 'good' ? '#ecfdf5'
              : it.tone === 'bad' ? '#fef2f2'
              : it.tone === 'warn' ? '#fffbeb'
              : '#eff6ff',
          }}>
            <div className="stat-main">
              <div className="label">{it.label}</div>
              <div className="value">
                {fmt(it.value)}
                {it.unit && <small style={{ marginLeft: 4 }}>{it.unit}</small>}
              </div>
            </div>
          </div>
        ))}
      </div>
    </Spin>
  )
}
