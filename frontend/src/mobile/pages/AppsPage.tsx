import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'

export default function AppsPage() {
  const navigate = useNavigate()
  const hasPermission = useAuthStore((s) => s.hasPermission)

  const apps = [
    { key: 'stock-check', title: '物料盘点', desc: '现场盘点 · 多人协同', emoji: '📋', path: '/stock-check', perm: ['materials.stock_check', 'read'] as const },
  ].filter((a) => hasPermission(a.perm[0], a.perm[1]))

  return (
    <div className="mobile-page mobile-page--with-tabbar">
      <div style={{ fontSize: 18, fontWeight: 700, color: '#1e293b', margin: '4px 0 12px' }}>应用</div>
      {apps.map((a) => (
        <div key={a.key} className="mobile-card" style={{ display: 'flex', alignItems: 'center', gap: 12 }} onClick={() => navigate(a.path)}>
          <div style={{ width: 44, height: 44, borderRadius: 10, background: '#eef0ff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22 }}>
            {a.emoji}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, fontSize: 14, color: '#1e293b' }}>{a.title}</div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>{a.desc}</div>
          </div>
          <span style={{ color: '#c7cbd6' }}>›</span>
        </div>
      ))}
      {apps.length === 0 && <div className="mobile-card" style={{ color: '#94a3b8', fontSize: 13 }}>暂无可用应用</div>}
    </div>
  )
}
