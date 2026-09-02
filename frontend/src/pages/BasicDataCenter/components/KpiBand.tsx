import { Card } from 'antd'
import type { ReactNode } from 'react'

export interface KpiItem {
  label: string
  value: ReactNode
  sub?: string
  go?: string
  accent?: 'brand' | 'success' | 'warning' | 'danger' | 'info' | 'purple' | 'gray'
  onClick?: () => void
}

const ACCENTS: Record<NonNullable<KpiItem['accent']>, [string, string]> = {
  brand: ['#5b5bd6', '#eef0fe'],
  success: ['#16a34a', '#f0fdf4'],
  warning: ['#d97706', '#fffbeb'],
  danger: ['#dc2626', '#fef2f2'],
  info: ['#0284c7', '#f0f9ff'],
  purple: ['#8b5cf6', '#f5f3ff'],
  gray: ['#64748b', '#f1f5f9'],
}

export default function KpiBand({ items }: { items: KpiItem[] }) {
  if (items.length === 0) return null
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${Math.min(items.length, 5)}, minmax(0, 1fr))`,
        gap: 12,
        marginBottom: 12,
      }}
    >
      {items.map((it, i) => {
        const [c] = ACCENTS[it.accent ?? 'brand']
        const clickable = !!it.onClick
        return (
          <Card
            key={i}
            size="small"
            className={clickable ? 'um-kpi' : undefined}
            styles={{ body: { padding: '12px 14px' } }}
            style={{ borderLeft: `3px solid ${c}`, cursor: clickable ? 'pointer' : undefined }}
            onClick={it.onClick}
          >
            <div style={{ fontSize: 'calc(12.5px * var(--font-size-scale))', color: '#94a3b8' }}>{it.label}</div>
            <div
              style={{
                fontSize: 'calc(20px * var(--font-size-scale))',
                fontWeight: 650,
                fontVariantNumeric: 'tabular-nums',
                lineHeight: 1.25,
                marginTop: 2,
              }}
            >
              {it.value}
            </div>
            {(it.go ?? it.sub) && (
              <div
                style={{
                  fontSize: 'calc(11.5px * var(--font-size-scale))',
                  marginTop: 2,
                  color: it.go ? c : '#94a3b8',
                  fontWeight: it.go ? 500 : 400,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {it.go ?? it.sub}
              </div>
            )}
          </Card>
        )
      })}
    </div>
  )
}
