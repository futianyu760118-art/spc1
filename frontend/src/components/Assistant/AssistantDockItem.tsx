import React from 'react'
import { Button } from 'antd'
import { ExportOutlined, RobotOutlined } from '@ant-design/icons'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAssistantLauncherStore } from '../../store/assistantLauncher'

interface Props {
  collapsed: boolean
}

const AssistantDockItem: React.FC<Props> = ({ collapsed }) => {
  const navigate = useNavigate()
  const location = useLocation()
  const undock = useAssistantLauncherStore(state => state.undock)

  if (location.pathname === '/ai-assistant') return null

  return (
    <div style={{
      flexShrink: 0,
      padding: collapsed ? '4px 12px 8px' : '4px 8px 8px',
      borderTop: '1px solid rgba(255,255,255,.06)',
    }}>
      <div
        role="button"
        tabIndex={0}
        aria-label="打开 AI 智能助手"
        title={collapsed ? 'AI 智能助手（展开侧栏可移出）' : 'AI 智能助手'}
        onClick={() => navigate('/ai-assistant')}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            navigate('/ai-assistant')
          }
        }}
        onMouseEnter={(event) => {
          event.currentTarget.style.background = 'rgba(255,255,255,.08)'
          event.currentTarget.style.color = '#fff'
        }}
        onMouseLeave={(event) => {
          event.currentTarget.style.background = 'transparent'
          event.currentTarget.style.color = 'rgba(255,255,255,.72)'
        }}
        style={{
          height: 36,
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: collapsed ? 0 : '0 12px',
          justifyContent: collapsed ? 'center' : 'flex-start',
          borderRadius: 8,
          color: 'rgba(255,255,255,.72)',
          cursor: 'pointer',
          transition: 'background .15s, color .15s',
        }}
      >
        <RobotOutlined style={{ fontSize: 18, color: '#a5b4fc' }} />
        {!collapsed && (
          <>
            <span style={{ flex: 1, fontSize: 'calc(14px * var(--font-size-scale))' }}>
              智能助手
            </span>
            <Button
              type="text"
              size="small"
              icon={<ExportOutlined />}
              title="移出侧边栏"
              aria-label="移出侧边栏"
              onClick={(event) => {
                event.stopPropagation()
                undock()
              }}
              style={{ color: 'rgba(255,255,255,.55)' }}
            />
          </>
        )}
      </div>
    </div>
  )
}

export default AssistantDockItem
