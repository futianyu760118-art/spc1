import React from 'react'

interface Props {
  icon: React.ReactNode
  label: string
  value: React.ReactNode
  unit?: string
  accent?: string
  accentBg?: string
  delta?: React.ReactNode
}

export default function StatCard({
  icon, label, value, unit, accent = '#5b5bd6', accentBg = '#eef0fe', delta,
}: Props) {
  return (
    <div
      className="sc-stat-card"
      style={{ ['--accent' as any]: accent, ['--accent-bg' as any]: accentBg }}
    >
      <div className="sc-stat-icon">{icon}</div>
      <div style={{ minWidth: 0 }}>
        <div className="sc-stat-label">{label}</div>
        <div className="sc-stat-value">{value}{unit && <small>{unit}</small>}</div>
        {delta}
      </div>
    </div>
  )
}
