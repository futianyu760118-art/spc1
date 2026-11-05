import { useEffect, useMemo, useState, type DragEvent } from 'react'
import { Button, Modal, Tag } from 'antd'
import {
  AppstoreOutlined,
  HolderOutlined,
  InboxOutlined,
  PushpinOutlined,
  UndoOutlined,
} from '@ant-design/icons'
import type { PermissionAwareItem } from './navUtils'
import {
  DEFAULT_SIDEBAR_MENU_PREFS,
  buildSidebarCustomizeModel,
  buildSidebarLayout,
  parkSidebarPage,
  pinSidebarPage,
  reorderKeys,
  restoreSidebarPage,
  type SidebarGroupModel,
  type SidebarMenuPrefs,
  type SidebarPageRef,
} from './sidebarMenuPrefs'

interface SidebarCustomizeModalProps {
  open: boolean
  onClose: () => void
  navTree: PermissionAwareItem[]
  prefs: SidebarMenuPrefs
  onChange: (next: SidebarMenuPrefs) => void
}

type PageZone = 'pinned' | 'module' | 'more'

type DragPayload =
  | { kind: 'page'; key: string; zone: PageZone; groupKey?: string }
  | { kind: 'group'; key: string }

export default function SidebarCustomizeModal({
  open,
  onClose,
  navTree,
  prefs,
  onChange,
}: SidebarCustomizeModalProps) {
  const [drag, setDrag] = useState<DragPayload | null>(null)
  const [overKey, setOverKey] = useState<string | null>(null)

  const model = useMemo(() => buildSidebarCustomizeModel(navTree, prefs), [navTree, prefs])
  const layout = useMemo(() => buildSidebarLayout(navTree, prefs), [navTree, prefs])

  useEffect(() => {
    if (!open) {
      setDrag(null)
      setOverKey(null)
    }
  }, [open])

  const apply = (next: SidebarMenuPrefs) => onChange(next)

  const startPageDrag = (
    event: DragEvent<HTMLElement>,
    page: SidebarPageRef,
    zone: PageZone,
    groupKey?: string,
  ) => {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', page.key)
    setDrag({ kind: 'page', key: page.key, zone, groupKey })
  }

  const startGroupDrag = (event: DragEvent<HTMLElement>, group: SidebarGroupModel) => {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', group.key)
    setDrag({ kind: 'group', key: group.key })
  }

  const endDrag = () => {
    setDrag(null)
    setOverKey(null)
  }

  const allowPageDrop = (
    event: DragEvent<HTMLElement>,
    zone: PageZone,
    groupKey?: string,
  ) => {
    if (drag?.kind !== 'page') return
    if (drag.zone === 'module' && zone === 'module' && (!groupKey || (drag.groupKey || '') !== groupKey)) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }

  const dropToZone = (event: DragEvent<HTMLElement>, zone: PageZone, groupKey?: string) => {
    event.preventDefault()
    event.stopPropagation()
    if (!drag || drag.kind !== 'page') {
      endDrag()
      return
    }
    if (zone === 'module' && drag.zone === 'module') {
      endDrag()
      return
    }
    if (zone === 'pinned') {
      apply(pinSidebarPage(prefs, drag.key))
    } else if (zone === 'more') {
      apply(parkSidebarPage(prefs, drag.key))
    } else {
      apply(restoreSidebarPage(prefs, drag.key))
    }
    endDrag()
  }

  const handlePageRowDrop = (
    event: DragEvent<HTMLElement>,
    zone: PageZone,
    groupKey: string | undefined,
    targetKey: string,
  ) => {
    event.preventDefault()
    event.stopPropagation()
    if (!drag || drag.kind !== 'page') {
      endDrag()
      return
    }
    const sameList = drag.zone === zone && (drag.groupKey || '') === (groupKey || '')
    if (!sameList) {
      dropToZone(event, zone, groupKey)
      return
    }
    if (zone === 'pinned') {
      apply({ ...prefs, pinned: reorderKeys(prefs.pinned, drag.key, targetKey) })
    } else if (zone === 'more') {
      apply({ ...prefs, parked: reorderKeys(prefs.parked, drag.key, targetKey) })
    } else if (groupKey) {
      const visibleKeys = (layout.groups.find(group => group.key === groupKey)?.pages || [])
        .map(page => page.key)
      apply({
        ...prefs,
        pageOrder: {
          ...prefs.pageOrder,
          [groupKey]: reorderKeys(visibleKeys, drag.key, targetKey),
        },
      })
    }
    endDrag()
  }

  const handleGroupDrop = (event: DragEvent<HTMLElement>, targetKey: string) => {
    if (!drag || drag.kind !== 'group') return
    event.preventDefault()
    event.stopPropagation()
    const keys = model.groups.map(group => group.key)
    apply({ ...prefs, groupOrder: reorderKeys(keys, drag.key, targetKey) })
    endDrag()
  }

  const markOver = (key: string) => setOverKey(key)
  const clearOver = (key: string) => setOverKey(current => (current === key ? null : current))

  const renderRowActions = (page: SidebarPageRef, zone: PageZone) => {
    if (zone === 'module') {
      return (
        <>
          <Button type="text" size="small" icon={<PushpinOutlined />} onClick={() => apply(pinSidebarPage(prefs, page.key))}>
            固顶
          </Button>
          <Button type="text" size="small" icon={<InboxOutlined />} onClick={() => apply(parkSidebarPage(prefs, page.key))}>
            移入更多
          </Button>
        </>
      )
    }
    return (
      <Button type="text" size="small" icon={<UndoOutlined />} onClick={() => apply(restoreSidebarPage(prefs, page.key))}>
        移回模块
      </Button>
    )
  }

  const renderPageRow = (page: SidebarPageRef, zone: PageZone, groupKey?: string) => {
    const rowKey = `${zone}:${groupKey || ''}:${page.key}`
    const className = [
      'sidebar-customize-row',
      overKey === rowKey ? 'is-over' : '',
      drag?.kind === 'page' && drag.key === page.key ? 'is-dragging' : '',
    ].filter(Boolean).join(' ')
    return (
      <div
        key={rowKey}
        className={className}
        draggable
        onDragStart={event => startPageDrag(event, page, zone, groupKey)}
        onDragEnd={endDrag}
        onDragOver={event => {
          allowPageDrop(event, zone, groupKey)
          if (drag?.kind === 'page' && event.defaultPrevented) markOver(rowKey)
        }}
        onDragLeave={() => clearOver(rowKey)}
        onDrop={event => handlePageRowDrop(event, zone, groupKey, page.key)}
      >
        <span className="sidebar-customize-icon">{page.item.icon || <AppstoreOutlined />}</span>
        <span className="sidebar-customize-label">{page.item.label}</span>
        {page.pathLabels.length > 0 && (
          <span className="sidebar-customize-sub">{page.pathLabels.join(' / ')}</span>
        )}
        {zone !== 'module' && (
          <Tag bordered={false} className="sidebar-customize-origin">{page.groupLabel}</Tag>
        )}
        <span className="sidebar-customize-actions">{renderRowActions(page, zone)}</span>
        <HolderOutlined className="sidebar-customize-handle" />
      </div>
    )
  }

  return (
    <Modal
      title="自定义菜单栏"
      open={open}
      onCancel={onClose}
      footer={null}
      width={660}
      centered
      maskClosable={false}
      destroyOnClose={false}
      wrapClassName="sidebar-customize-modal"
    >
      <div className="sidebar-customize-body">
        <div
          className="sidebar-customize-section"
          onDragOver={event => allowPageDrop(event, 'pinned')}
          onDrop={event => dropToZone(event, 'pinned')}
        >
          <div className="sidebar-customize-section-title">固顶快捷入口</div>
          {layout.pinned.length === 0 ? (
            <div className="sidebar-customize-hint">将页面拖到这里，或点击页面行内的「固顶」</div>
          ) : (
            layout.pinned.map(page => renderPageRow(page, 'pinned'))
          )}
        </div>

        <div
          className="sidebar-customize-section"
          onDragOver={event => allowPageDrop(event, 'module')}
          onDrop={event => dropToZone(event, 'module')}
        >
          <div className="sidebar-customize-section-title">模块菜单</div>
          {model.groups.map(group => {
            const headKey = `group:${group.key}`
            const visiblePages = layout.groups.find(item => item.key === group.key)?.pages || []
            const isLeafGroup = !group.item.children || group.item.children.length === 0
            const leafPage = isLeafGroup ? group.pages[0] : undefined
            return (
              <div
                key={group.key}
                className="sidebar-customize-group"
                onDragOver={event => allowPageDrop(event, 'module', group.key)}
                onDrop={event => dropToZone(event, 'module', group.key)}
              >
                <div
                  className={[
                    'sidebar-customize-row',
                    'sidebar-customize-group-head',
                    overKey === headKey ? 'is-over' : '',
                    drag?.kind === 'group' && drag.key === group.key ? 'is-dragging' : '',
                  ].filter(Boolean).join(' ')}
                  draggable
                  onDragStart={event => startGroupDrag(event, group)}
                  onDragEnd={endDrag}
                  onDragOver={event => {
                    if (drag?.kind !== 'group') return
                    event.preventDefault()
                    event.dataTransfer.dropEffect = 'move'
                    markOver(headKey)
                  }}
                  onDragLeave={() => clearOver(headKey)}
                  onDrop={event => handleGroupDrop(event, group.key)}
                >
                  <span className="sidebar-customize-icon">{group.icon || <AppstoreOutlined />}</span>
                  <span className="sidebar-customize-label">{group.label}</span>
                  {leafPage && (
                    <span className="sidebar-customize-actions">
                      <Button type="text" size="small" icon={<PushpinOutlined />} onClick={() => apply(pinSidebarPage(prefs, leafPage.key))}>
                        固顶
                      </Button>
                      <Button type="text" size="small" icon={<InboxOutlined />} onClick={() => apply(parkSidebarPage(prefs, leafPage.key))}>
                        移入更多
                      </Button>
                    </span>
                  )}
                  <span className="sidebar-customize-group-count">{visiblePages.length}</span>
                  <HolderOutlined className="sidebar-customize-handle" />
                </div>
                {visiblePages.length === 0 ? (
                  <div className="sidebar-customize-hint">该模块页面已全部固顶或收纳</div>
                ) : isLeafGroup ? null : (
                  visiblePages.map(page => renderPageRow(page, 'module', group.key))
                )}
              </div>
            )
          })}
        </div>

        <div
          className="sidebar-customize-section"
          onDragOver={event => allowPageDrop(event, 'more')}
          onDrop={event => dropToZone(event, 'more')}
        >
          <div className="sidebar-customize-section-title">更多收纳</div>
          {layout.parked.length === 0 ? (
            <div className="sidebar-customize-hint">暂无收纳页面。侧栏装不下的模块会自动出现在「更多」</div>
          ) : (
            layout.parked.map(page => renderPageRow(page, 'more'))
          )}
        </div>
      </div>

      <div className="sidebar-customize-footer">
        <Button
          type="text"
          danger
          onClick={() => apply({ ...DEFAULT_SIDEBAR_MENU_PREFS, pageOrder: {} })}
        >
          恢复默认
        </Button>
        <Button type="primary" onClick={onClose}>完成</Button>
      </div>
    </Modal>
  )
}
