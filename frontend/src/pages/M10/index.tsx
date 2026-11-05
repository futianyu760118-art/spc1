import { useMemo, useState } from 'react'
import { ExportOutlined } from '@ant-design/icons'

// M10 微系统内嵌页：视觉与 M10 原 demo（统一门户 portal.html）保持一致
// 深蓝渐变头 + 白色卡片 + 浅灰底；页签切换 M10 各工作台，右侧可新窗口打开。
const TABS = [
  { key: 'portal', label: '门户', path: '/' },
  { key: 'plm2', label: '研发工作台', path: '/plm2' },
  { key: 'taskhub', label: '待办总表', path: '/taskhub' },
  { key: 'hlc', label: '人力后勤', path: '/hlc' },
]

function m10Base(): string {
  const env = (import.meta as any).env?.VITE_M10_BASE_URL?.trim()
  if (env) return env.replace(/\/$/, '')
  const host = window.location.hostname || '127.0.0.1'
  if (window.location.protocol === 'https:') return 'https://wxt.hengyou-soft.com'
  return `http://${host}:4173`
}

export default function M10Page() {
  const [tab, setTab] = useState('portal')
  const base = useMemo(m10Base, [])
  const cur = TABS.find(x => x.key === tab) || TABS[0]
  const frameUrl = useMemo(() => base + cur.path, [base, cur])
  const openUrl = base + cur.path

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 96px)', background: '#f4f6fa' }}>
      {/* 头部与 M10 门户 demo 一致：深蓝渐变 + 标题 + 副标题 + 页签 */}
      <div style={{ background: 'linear-gradient(135deg, #10233b, #1b3d63)', color: '#fff', padding: '18px 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <div style={{ margin: 0, fontSize: 20, fontWeight: 800, lineHeight: 1.3 }}>M10 微系统 · 统一门户</div>
            <div style={{ marginTop: 4, fontSize: 13, opacity: 0.75 }}>岗位与个人运营微系统 · 与 PLM / SPC / 会议 / HLC 实时同步</div>
          </div>
          <button
            onClick={() => window.open(openUrl, '_blank', 'noopener')}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 5, cursor: 'pointer',
              border: '1px solid rgba(255,255,255,.4)', background: 'rgba(255,255,255,.12)',
              color: '#fff', borderRadius: 9, padding: '6px 12px', fontSize: 13,
            }}
          >
            <ExportOutlined /> 新窗口打开
          </button>
        </div>
        <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              style={{
                cursor: 'pointer', fontSize: 12, padding: '5px 13px', borderRadius: 20,
                border: '1px solid rgba(255,255,255,.35)',
                background: tab === t.key ? '#1767c9' : 'rgba(255,255,255,.12)',
                color: tab === t.key ? '#fff' : '#dbe7f5',
              }}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      <iframe
        src={frameUrl}
        style={{ flex: 1, width: '100%', border: 0, background: '#fff' }}
        allow="camera; microphone; fullscreen"
        referrerPolicy="no-referrer"
        title="M10 微系统"
      />
    </div>
  )
}
