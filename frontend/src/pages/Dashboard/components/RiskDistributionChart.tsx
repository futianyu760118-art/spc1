interface RiskDistributionChartProps {
  summary: {
    red_count: number
    yellow_count: number
    blue_count: number
    green_count: number
  } | null
}

export default function RiskDistributionChart({ summary }: RiskDistributionChartProps) {
  if (!summary) return null

  const total = summary.red_count + summary.yellow_count + summary.blue_count + summary.green_count
  if (total === 0) return null

  const segments = [
    { label: '高风险', count: summary.red_count, color: '#e11d48' },
    { label: '中风险', count: summary.yellow_count, color: '#d97706' },
    { label: '低风险', count: summary.blue_count, color: '#3b82f6' },
    { label: '正常', count: summary.green_count, color: '#059669' },
  ]

  return (
    <div className="card-modern" style={{ padding: '20px 24px', marginBottom: 18 }}>
      <h3 className="text-sm font-semibold m-0 mb-3" style={{ color: '#475569' }}>风险分布</h3>
      <div style={{ display: 'flex', borderRadius: 8, overflow: 'hidden', height: 10 }}>
        {segments.map((seg) => (
          <div
            key={seg.label}
            style={{
              width: `${(seg.count / total) * 100}%`,
              background: seg.color,
              transition: 'width .3s',
            }}
          />
        ))}
      </div>
      <div className="flex gap-5 mt-3">
        {segments.map((seg) => (
          <div key={seg.label} className="flex items-center gap-1" style={{ fontSize: 12, color: '#64748b' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: seg.color, display: 'inline-block' }} />
            {seg.label} {seg.count}
          </div>
        ))}
      </div>
    </div>
  )
}
