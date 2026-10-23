import React, { useEffect, useRef, useState } from 'react'
import { Button } from 'antd'
import { RobotOutlined, CloseOutlined } from '@ant-design/icons'
import ChatPanel from './ChatPanel'
import { useAssistantChat } from './useAssistantChat'

// 悬浮球尺寸
const BALL_SIZE = 52
// 收起后贴边的可见宽度
const COLLAPSED_TAB_WIDTH = 22
// 判定为拖动（而非点击）的位移阈值（px）
const DRAG_THRESHOLD = 5
// 距视口边缘的最小间距
const EDGE_MARGIN = 8
// 闲置多久后自动收起（ms）
const IDLE_TIMEOUT = 4000
// 仅当悬浮球位于距右边沿该范围内时，闲置才自动收起
const COLLAPSE_ZONE = 260

// 聊天窗口尺寸
const WIN_WIDTH = 400
const WIN_HEIGHT = 620

const FloatingAssistant: React.FC = () => {
  const [open, setOpen] = useState(false)
  const { messages, loading, send, skills, loadSkills, clearMessages, stopStreaming, confirmWrite, cancelWrite } = useAssistantChat()

  // 以距右、距底的偏移存储位置，窗口缩放时仍贴右下
  const [pos, setPos] = useState({ right: 24, bottom: 24 })
  const [collapsed, setCollapsed] = useState(false)
  const [hovering, setHovering] = useState(false)
  const [dragging, setDragging] = useState(false)

  const dragRef = useRef({ active: false, moved: false, startX: 0, startY: 0, startRight: 0, startBottom: 0 })
  const idleTimerRef = useRef<number | null>(null)

  useEffect(() => {
    if (open && skills.length === 0) {
      loadSkills()
    }
  }, [open, skills.length, loadSkills])

  // 任何交互（悬停 / 拖动 / 打开面板）都应取消收起状态
  useEffect(() => {
    if (hovering || dragging || open) {
      setCollapsed(false)
    }
  }, [hovering, dragging, open])

  // 闲置自动收起到右侧边
  useEffect(() => {
    if (idleTimerRef.current) {
      window.clearTimeout(idleTimerRef.current)
      idleTimerRef.current = null
    }
    if (!open && !dragging && !hovering) {
      idleTimerRef.current = window.setTimeout(() => {
        setPos(p => {
          // 仅当悬浮球在右侧区域内时才收起，避免把左侧的球强行拉到右边
          if (p.right <= COLLAPSE_ZONE) {
            setCollapsed(true)
          }
          return p
        })
      }, IDLE_TIMEOUT)
    }
    return () => {
      if (idleTimerRef.current) window.clearTimeout(idleTimerRef.current)
    }
  }, [open, dragging, hovering, pos.right, pos.bottom])

  // ESC 关闭窗口
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const handlePointerDown = (e: React.PointerEvent) => {
    if (open) return
    e.preventDefault()
    setDragging(true)
    dragRef.current = {
      active: true,
      moved: false,
      startX: e.clientX,
      startY: e.clientY,
      startRight: pos.right,
      startBottom: pos.bottom,
    }
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  }

  const handlePointerMove = (e: React.PointerEvent) => {
    const ds = dragRef.current
    if (!ds.active) return
    const dx = e.clientX - ds.startX
    const dy = e.clientY - ds.startY
    if (!ds.moved && (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD)) {
      ds.moved = true
      setCollapsed(false)
    }
    if (ds.moved) {
      const maxRight = window.innerWidth - BALL_SIZE - EDGE_MARGIN
      const maxBottom = window.innerHeight - BALL_SIZE - EDGE_MARGIN
      let newRight = ds.startRight - dx
      let newBottom = ds.startBottom - dy
      newRight = Math.max(EDGE_MARGIN, Math.min(maxRight, newRight))
      newBottom = Math.max(EDGE_MARGIN, Math.min(maxBottom, newBottom))
      setPos({ right: newRight, bottom: newBottom })
    }
  }

  const handlePointerUp = (e: React.PointerEvent) => {
    const ds = dragRef.current
    if (!ds.active) return
    ds.active = false
    setDragging(false)
    try {
      ;(e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId)
    } catch {
      /* ignore */
    }
    // 未移动 → 视为点击
    if (!ds.moved) {
      if (collapsed) {
        setCollapsed(false)
      } else {
        setOpen(true)
      }
    }
  }

  // 计算聊天窗口位置（跟随悬浮球，并钳制在视口内）
  const computeWinStyle = (): React.CSSProperties => {
    const vw = window.innerWidth
    const vh = window.innerHeight
    const winW = Math.min(WIN_WIDTH, vw - 16)
    const winH = Math.min(WIN_HEIGHT, vh - 32)
    // 水平：与球的右边缘对齐，但保证不溢出左侧
    const maxRight = Math.max(EDGE_MARGIN, vw - winW - EDGE_MARGIN)
    const right = Math.min(Math.max(pos.right, EDGE_MARGIN), maxRight)
    // 垂直：默认在球上方；空间不足时下移以保持顶部在视口内
    const desiredBottom = pos.bottom + BALL_SIZE + 12
    const maxBottom = Math.max(EDGE_MARGIN, vh - winH - EDGE_MARGIN)
    const bottom = Math.min(Math.max(desiredBottom, EDGE_MARGIN), maxBottom)
    return { right, bottom, width: winW, height: winH }
  }

  return (
    <>
      {/* 聊天窗口（替代原侧边 Drawer） */}
      {open && (
        <div
          style={{
            position: 'fixed',
            ...computeWinStyle(),
            background: '#fff',
            borderRadius: 16,
            boxShadow: '0 24px 64px rgba(15,23,42,.22), 0 6px 16px rgba(15,23,42,.08)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            zIndex: 101,
            animation: 'ai-win-in .22s cubic-bezier(.21,1.02,.73,1)',
          }}
        >
          {/* 标题栏 */}
          <div
            style={{
              padding: '12px 14px',
              background: 'linear-gradient(135deg, #3b82f6 0%, #6366f1 100%)',
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexShrink: 0,
              boxShadow: '0 2px 8px rgba(59,130,246,.18)',
            }}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, fontSize: 15, letterSpacing: .3 }}>
              <RobotOutlined style={{ fontSize: 18 }} />
              AI 智能助手
            </span>
            <Button
              type="text"
              size="small"
              icon={<CloseOutlined />}
              onClick={() => setOpen(false)}
              style={{ color: '#fff', width: 28, height: 28, borderRadius: 8 }}
            />
          </div>

          {/* 主体 */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, background: '#f8fafc' }}>
            <ChatPanel
              messages={messages}
              loading={loading}
              skills={skills}
              onSend={send}
              onClear={clearMessages}
              onStop={stopStreaming}
              onConfirm={confirmWrite}
              onCancelConfirmation={cancelWrite}
            />
          </div>
        </div>
      )}

      {/* 收起状态下贴右边的细条（点击展开） */}
      {!open && collapsed && (
        <div
          onClick={() => setCollapsed(false)}
          title="展开 AI 智能助手"
          style={{
            position: 'fixed',
            right: 0,
            bottom: pos.bottom,
            width: COLLAPSED_TAB_WIDTH,
            height: BALL_SIZE,
            borderRadius: `${COLLAPSED_TAB_WIDTH}px 0 0 ${COLLAPSED_TAB_WIDTH}px`,
            background: 'linear-gradient(135deg, #3b82f6 0%, #6366f1 100%)',
            boxShadow: '-2px 6px 16px rgba(59,130,246,.3)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            cursor: 'pointer',
            zIndex: 100,
            userSelect: 'none',
            transition: 'bottom .2s ease',
          }}
        >
          <RobotOutlined style={{ fontSize: 14 }} />
        </div>
      )}

      {/* 展开的悬浮球（窗口打开时隐藏） */}
      {!open && !collapsed && (
        <div
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onMouseEnter={() => setHovering(true)}
          onMouseLeave={() => setHovering(false)}
          title="AI 智能助手（可拖动，闲置自动收起）"
          style={{
            position: 'fixed',
            right: pos.right,
            bottom: pos.bottom,
            width: BALL_SIZE,
            height: BALL_SIZE,
            borderRadius: '50%',
            background: 'linear-gradient(135deg, #3b82f6 0%, #6366f1 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            cursor: dragging ? 'grabbing' : 'grab',
            zIndex: 100,
            userSelect: 'none',
            touchAction: 'none',
            transition: dragging ? 'none' : 'right .25s ease, bottom .2s ease, transform .2s ease, box-shadow .2s ease',
            transform: hovering && !dragging ? 'scale(1.08)' : 'scale(1)',
            boxShadow: hovering ? '0 10px 28px rgba(59,130,246,.5)' : '0 6px 20px rgba(59,130,246,.35)',
          }}
        >
          <RobotOutlined style={{ fontSize: 24 }} />
        </div>
      )}

      <style>{`
        @keyframes ai-win-in {
          from { opacity: 0; transform: translateY(12px) scale(.96); }
          to   { opacity: 1; transform: translateY(0) scale(1); }
        }
      `}</style>
    </>
  )
}

export default FloatingAssistant
