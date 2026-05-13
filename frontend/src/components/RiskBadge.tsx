const riskConfig: Record<string, { bg: string; dot: string; text: string; label: string }> = {
  red:    { bg: 'rgba(225,29,72,.08)', dot: '#e11d48', text: '#be123c', label: '高风险' },
  yellow: { bg: 'rgba(217,119,6,.08)', dot: '#d97706', text: '#b45309', label: '中风险' },
  blue:   { bg: 'rgba(59,130,246,.08)', dot: '#3b82f6', text: '#2563eb', label: '低风险' },
  green:  { bg: 'rgba(5,150,105,.08)', dot: '#059669', text: '#047857', label: '正常' },
}

interface RiskBadgeProps {
  level: string | null | undefined
  onClick?: () => void
}

export default function RiskBadge({ level, onClick }: RiskBadgeProps) {
  if (!level || !riskConfig[level]) {
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '2px 10px', borderRadius: 20, background: 'rgba(0,0,0,.04)', color: '#94a3b8', fontSize: 12 }}>
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#cbd5e1' }} />
        未评估
      </span>
    )
  }
  const { bg, dot, text, label } = riskConfig[level]
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        padding: '2px 10px',
        borderRadius: 20,
        background: bg,
        color: text,
        fontSize: 12,
        fontWeight: 500,
        cursor: onClick ? 'pointer' : 'default',
      }}
      onClick={onClick}
    >
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: dot }} />
      {label}
    </span>
  )
}
