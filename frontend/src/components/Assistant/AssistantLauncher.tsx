import React, { useCallback, useEffect, useRef, useState } from 'react'
import { RobotOutlined } from '@ant-design/icons'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAssistantLauncherStore } from '../../store/assistantLauncher'
import './assistant-launcher.css'

const BALL_SIZE = 52
const EDGE_MARGIN = 8
const DRAG_THRESHOLD = 5
const DOCK_OFFSET = 28

const AssistantLauncher: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const mode = useAssistantLauncherStore(state => state.mode)
  const position = useAssistantLauncherStore(state => state.position)
  const setPosition = useAssistantLauncherStore(state => state.setPosition)
  const dock = useAssistantLauncherStore(state => state.dock)
  const [dragging, setDragging] = useState(false)
  const [hovering, setHovering] = useState(false)
  const [dockReady, setDockReady] = useState(false)
  const dragRef = useRef({
    active: false,
    moved: false,
    startX: 0,
    startY: 0,
    startRight: 0,
    startBottom: 0,
  })

  const clampPosition = useCallback((right: number, bottom: number) => {
    const maxRight = Math.max(EDGE_MARGIN, window.innerWidth - BALL_SIZE - EDGE_MARGIN)
    const maxBottom = Math.max(EDGE_MARGIN, window.innerHeight - BALL_SIZE - EDGE_MARGIN)
    return {
      right: Math.min(Math.max(EDGE_MARGIN, right), maxRight),
      bottom: Math.min(Math.max(EDGE_MARGIN, bottom), maxBottom),
    }
  }, [])

  const isNearSidebar = useCallback((clientX: number) => {
    const sidebar = document.querySelector('.sidebar-modern')
    const sidebarRight = sidebar ? sidebar.getBoundingClientRect().right : 0
    return sidebarRight > 0 && clientX <= sidebarRight + DOCK_OFFSET
  }, [])

  const clearDockTarget = useCallback(() => {
    setDockReady(false)
    document.querySelector('.sidebar-modern')?.classList.remove('assistant-dock-target')
  }, [])

  useEffect(() => () => {
    document.querySelector('.sidebar-modern')?.classList.remove('assistant-dock-target')
  }, [])

  useEffect(() => {
    const handleResize = () => {
      const next = clampPosition(position.right, position.bottom)
      if (next.right !== position.right || next.bottom !== position.bottom) {
        setPosition(next)
      }
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [position, clampPosition, setPosition])

  if (mode === 'docked' || location.pathname === '/ai-assistant') return null

  const handlePointerDown = (event: React.PointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) return
    event.preventDefault()
    setDragging(true)
    dragRef.current = {
      active: true,
      moved: false,
      startX: event.clientX,
      startY: event.clientY,
      startRight: position.right,
      startBottom: position.bottom,
    }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  const handlePointerMove = (event: React.PointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current
    if (!drag.active) return
    const dx = event.clientX - drag.startX
    const dy = event.clientY - drag.startY
    if (!drag.moved && (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD)) {
      drag.moved = true
    }
    if (!drag.moved) return
    setPosition(clampPosition(drag.startRight - dx, drag.startBottom - dy))
    const nearSidebar = isNearSidebar(event.clientX)
    setDockReady(nearSidebar)
    document.querySelector('.sidebar-modern')?.classList.toggle('assistant-dock-target', nearSidebar)
  }

  const handlePointerUp = (event: React.PointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current
    if (!drag.active) return
    drag.active = false
    setDragging(false)
    try {
      event.currentTarget.releasePointerCapture(event.pointerId)
    } catch {
      /* ignore */
    }
    if (!drag.moved) {
      navigate('/ai-assistant')
      return
    }
    const nearSidebar = isNearSidebar(event.clientX)
    clearDockTarget()
    if (nearSidebar) {
      dock()
    }
  }

  const handlePointerCancel = () => {
    dragRef.current.active = false
    setDragging(false)
    clearDockTarget()
  }

  return (
    <button
      type="button"
      aria-label="打开 AI 智能助手"
      title="AI 智能助手（拖动可移动，拖到左侧侧栏可收纳）"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerCancel}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          navigate('/ai-assistant')
        }
      }}
      style={{
        position: 'fixed',
        right: position.right,
        bottom: position.bottom,
        width: BALL_SIZE,
        height: BALL_SIZE,
        border: 'none',
        borderRadius: '50%',
        background: 'linear-gradient(135deg, #7a7de6 0%, #5b5bd6 100%)',
        color: '#fff',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: dragging ? 'grabbing' : 'grab',
        zIndex: 100,
        userSelect: 'none',
        touchAction: 'none',
        transform: dockReady ? 'scale(1.08)' : (hovering && !dragging ? 'scale(1.08)' : 'scale(1)'),
        boxShadow: dockReady
          ? '0 0 0 4px rgba(91,91,214,.35), 0 10px 28px rgba(91,91,214,.45)'
          : (hovering && !dragging
            ? '0 10px 28px rgba(91,91,214,.45)'
            : '0 6px 20px rgba(91,91,214,.32)'),
        transition: dragging ? 'none' : 'transform .2s ease, box-shadow .2s ease',
        opacity: dragging ? 0.92 : 1,
      }}
    >
      <RobotOutlined style={{ fontSize: 24 }} />
    </button>
  )
}

export default AssistantLauncher
