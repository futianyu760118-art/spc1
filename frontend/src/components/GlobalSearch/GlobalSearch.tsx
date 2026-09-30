import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Modal } from 'antd'
import { SearchOutlined, CloseOutlined, FileTextOutlined, ClockCircleOutlined, StarOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import {
  flattenPages,
  searchPages,
  getRecentRoutes,
  pushRecentRoute,
  resetRecent,
  type ScoredPage,
  type SearchableMenu,
} from './fuzzyMatch'

/** 将标题按命中下标拆成段，命中段用 <mark> 高亮。 */
function highlightTitle(title: string, indices: number[]): React.ReactNode {
  if (!indices.length) return title
  const set = new Set(indices)
  const out: React.ReactNode[] = []
  let buf = ''
  let inMatch = false
  for (let i = 0; i < title.length; i++) {
    const isMatch = set.has(i)
    if (isMatch === inMatch) {
      buf += title.charAt(i)
    } else {
      if (buf) out.push(inMatch ? <mark key={i}>{buf}</mark> : buf)
      buf = title.charAt(i)
      inMatch = isMatch
    }
  }
  if (buf) out.push(inMatch ? <mark key="end">{buf}</mark> : buf)
  return out
}

const ResultItem: React.FC<{
  item: ScoredPage
  selected: boolean
  hasQuery: boolean
  onHover: () => void
  onClick: () => void
}> = ({ item, selected, hasQuery, onHover, onClick }) => {
  const p = item.page
  const Icon = item.isRecent && !hasQuery ? ClockCircleOutlined : FileTextOutlined
  return (
    <div
      className={`gs-result-item${selected ? ' selected' : ''}`}
      data-grouped={!hasQuery}
      onMouseEnter={onHover}
      onClick={onClick}
    >
      <Icon className="gs-result-icon" />
      {hasQuery && item.isRecent && <StarOutlined style={{ fontSize: 11, color: '#6366f1' }} title="最近访问" />}
      <span className="gs-result-title">
        {highlightTitle(p.title, item.indices)}
        {item.hit === 'pinyin' && <span className="gs-result-pinyin">[{p.pinyin}]</span>}
      </span>
      <span className="gs-result-meta">
        <span className="gs-module-tag">{p.module}</span>
        <span className="gs-result-path">{p.routePath}</span>
      </span>
    </div>
  )
}

const GlobalSearch: React.FC<{ items: SearchableMenu[] }> = ({ items }) => {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [recent, setRecent] = useState<string[]>([])
  const [selected, setSelected] = useState(0)
  const [recentVersion, setRecentVersion] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const resultsRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  const pages = useMemo(() => flattenPages(items), [items])

  const results = useMemo<ScoredPage[]>(
    () => searchPages(query, pages, recent),
    [query, pages, recent],
  )

  // 最近访问需在打开时刷新一次（外部可能改动 localStorage）
  useEffect(() => {
    if (open) {
      setRecent(getRecentRoutes())
      setQuery('')
      setSelected(0)
      const t = window.setTimeout(() => inputRef.current?.focus(), 30)
      return () => window.clearTimeout(t)
    }
  }, [open, recentVersion])

  // 选中项变化时滚入视口
  useEffect(() => {
    const root = resultsRef.current
    if (!root) return
    const el = root.querySelector('.gs-result-item.selected') as HTMLElement | null
    if (el) el.scrollIntoView({ block: 'nearest' })
  }, [selected, results])

  const openItem = useCallback(
    (item: ScoredPage | undefined) => {
      if (!item) return
      const next = pushRecentRoute(item.page.routePath)
      setRecent(next)
      setOpen(false)
      navigate(item.page.routePath)
    },
    [navigate],
  )

  const moveSelection = useCallback(
    (delta: number) => {
      const n = results.length
      if (n === 0) return
      setSelected((cur) => (cur + delta + n) % n)
    },
    [results.length],
  )

  // Ctrl/Cmd + K 唤起全局搜索
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen((o) => !o)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const onInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      moveSelection(1)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      moveSelection(-1)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      openItem(results[selected])
    }
  }

  const handleResetRecent = () => {
    resetRecent()
    setRecent([])
    setRecentVersion((v) => v + 1)
  }

  const hasQuery = query.trim().length > 0

  // 分组渲染（空查询时按 group 字段聚合）
  let lastGroup: string | null = null
  return (
    <>
      <div
        className="tbv2-gsearch"
        onClick={() => setOpen(true)}
        title="搜索页面（Ctrl+K）"
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            setOpen(true)
          }
        }}
      >
        <SearchOutlined className="tbv2-gsearch-icon" />
        <span className="tbv2-gsearch-text">搜索页面…</span>
        <kbd className="tbv2-gsearch-kbd">Ctrl K</kbd>
      </div>

      <Modal
        open={open}
        onCancel={() => setOpen(false)}
        footer={null}
        closable={false}
        maskClosable
        mask
        width={640}
        zIndex={1100}
        style={{ top: '12vh', maxWidth: '92vw', margin: '0 auto', paddingBottom: 0 }}
        styles={{ body: { padding: 0 }, mask: { background: 'rgba(0,0,0,0.3)', backdropFilter: 'blur(2px)' } }}
        className="gs-modal"
        destroyOnClose
      >
        <div className="gs-palette">
          <div className="gs-input-wrap">
            <SearchOutlined className="gs-input-icon" />
            <input
              ref={inputRef}
              type="text"
              className="gs-input"
              placeholder="搜索页面（标题、路径或拼音首字母）…"
              autoComplete="off"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value)
                setSelected(0)
              }}
              onKeyDown={onInputKeyDown}
            />
            <div className="gs-close" onClick={() => setOpen(false)} title="关闭 (Esc)">
              <CloseOutlined style={{ fontSize: 12 }} />
            </div>
          </div>

          <div className="gs-results" ref={resultsRef}>
            {results.length === 0 ? (
              <div className="gs-empty">未找到匹配的页面</div>
            ) : !hasQuery ? (
              results.map((item, idx) => {
                const showGroup = item.group !== lastGroup
                lastGroup = item.group ?? null
                return (
                  <div key={`${item.page.code}-${idx}`}>
                    {showGroup && <div className="gs-group-title">{item.group}</div>}
                    <ResultItem
                      item={item}
                      selected={idx === selected}
                      hasQuery={hasQuery}
                      onHover={() => setSelected(idx)}
                      onClick={() => openItem(item)}
                    />
                  </div>
                )
              })
            ) : (
              results.map((item, idx) => (
                <ResultItem
                  key={`${item.page.code}-${idx}`}
                  item={item}
                  selected={idx === selected}
                  hasQuery={hasQuery}
                  onHover={() => setSelected(idx)}
                  onClick={() => openItem(item)}
                />
              ))
            )}
          </div>

          <div className="gs-footer">
            <div className="gs-footer-keys">
              <span><kbd>↑</kbd><kbd>↓</kbd> 导航</span>
              <span><kbd>↵</kbd> 打开</span>
              <span><kbd>Esc</kbd> 关闭</span>
            </div>
            <div className="gs-footer-actions">
              <button type="button" className="gs-reset-btn" onClick={handleResetRecent} title="清空最近访问">
                重置最近访问
              </button>
              <span>共 {results.length} 个结果</span>
            </div>
          </div>
        </div>
      </Modal>
    </>
  )
}

export default GlobalSearch
