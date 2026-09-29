import type { CSSProperties, ReactNode } from 'react'

export type StatCard = {
  key: string
  label: string
  value: number | string
  unit?: string
  icon?: ReactNode
  hint?: string
  // 较上期变化：count 为差值（正负皆可），goodWhenDown 表示「该方向是改善」（如处理时长下降为好）
  delta?: { count: number; unit?: string; goodWhenDown?: boolean }
  tone?: 'default' | 'info' | 'warning' | 'danger' | 'success' | 'muted'
  onClick?: () => void
  active?: boolean
}

const TONE: Record<string, { color: string; bg: string }> = {
  default: { color: '#5b5bd6', bg: '#eef0fe' },
  info: { color: '#0284c7', bg: '#f0f9ff' },
  warning: { color: '#d97706', bg: '#fffbeb' },
  danger: { color: '#dc2626', bg: '#fef2f2' },
  success: { color: '#16a34a', bg: '#f0fdf4' },
  muted: { color: '#64748b', bg: '#f1f5f9' },
}

function DeltaText({ delta }: { delta: NonNullable<StatCard['delta']> }) {
  if (!delta.count) return <div className="sc-stat-delta flat">与上期持平</div>
  const down = delta.count < 0
  const isGood = delta.goodWhenDown ? down : !down
  return (
    <div className={`sc-stat-delta ${isGood ? 'up' : 'down'}`}>
      {down ? '▼' : '▲'} {Math.abs(delta.count).toLocaleString()}{delta.unit || ''} 较上期
    </div>
  )
}

export default function ApprovalStatsCards({ cards }: { cards: StatCard[] }) {
  return (
    <div className="ac-kpi-band">
      {cards.map(c => {
        const tone = TONE[c.tone || 'default']
        return (
          <div
            key={c.key}
            className={`sc-stat-card ac-stat-card${c.onClick ? ' clickable' : ''}${c.active ? ' on' : ''}`}
            style={{ '--accent': tone.color, '--accent-bg': tone.bg } as CSSProperties}
            onClick={c.onClick}
          >
            {c.icon ? <div className="sc-stat-icon">{c.icon}</div> : null}
            <div className="sc-stat-main">
              <div className="sc-stat-label">{c.label}</div>
              <div className="sc-stat-value">
                {c.value}{c.unit ? <small>{c.unit}</small> : null}
              </div>
              {c.delta ? <DeltaText delta={c.delta} />
                : c.hint ? <div className="sc-stat-delta flat">{c.hint}</div> : null}
            </div>
          </div>
        )
      })}
    </div>
  )
}
