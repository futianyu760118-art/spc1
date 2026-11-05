import { AppstoreOutlined, ControlOutlined } from '@ant-design/icons'
import type { SidebarMoreSection } from './sidebarMenuPrefs'

interface SidebarMorePanelProps {
  sections: SidebarMoreSection[]
  onNavigate: (key: string) => void
  onCustomize: () => void
}

export default function SidebarMorePanel({ sections, onNavigate, onCustomize }: SidebarMorePanelProps) {
  return (
    <div className="sidebar-more-panel">
      {sections.map(section => (
        <div key={section.key} className="sidebar-more-section">
          <div className="sidebar-more-section-title">{section.label}</div>
          {section.pages.map(page => (
            <button
              key={page.key}
              type="button"
              className="sidebar-more-item"
              onClick={() => onNavigate(page.key)}
            >
              <span className="sidebar-more-item-icon">{page.item.icon || <AppstoreOutlined />}</span>
              <span className="sidebar-more-item-label">{page.item.label}</span>
              {page.pathLabels.length > 0 && (
                <span className="sidebar-more-item-sub">{page.pathLabels.join(' / ')}</span>
              )}
            </button>
          ))}
        </div>
      ))}
      <button type="button" className="sidebar-more-customize" onClick={onCustomize}>
        <ControlOutlined />
        <span>自定义菜单栏</span>
      </button>
    </div>
  )
}
