import React from 'react'
import { Tag, Space, Typography } from 'antd'
import {
  ExclamationCircleOutlined,
  WarningOutlined,
  InfoCircleOutlined,
  CheckCircleOutlined,
  RightOutlined,
} from '@ant-design/icons'

const { Text } = Typography

interface ActionItem {
  priority: 'critical' | 'high' | 'medium' | 'low'
  category: string
  title: string
  description: string
  action_type: string
  action_params: any
}

interface Props {
  title: string
  actions: ActionItem[]
  context?: string
  onActionClick?: (action: ActionItem) => void
}

const priorityConfig: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  critical: { color: '#ff4d4f', icon: <ExclamationCircleOutlined />, label: '紧急' },
  high: { color: '#fa8c16', icon: <WarningOutlined />, label: '重要' },
  medium: { color: '#1890ff', icon: <InfoCircleOutlined />, label: '关注' },
  low: { color: '#52c41a', icon: <CheckCircleOutlined />, label: '一般' },
}

const categoryLabels: Record<string, string> = {
  delivery: '交付',
  overdue: '逾期',
  risk: '风险',
  planning: '计划',
  procurement: '采购',
  summary: '总结',
  info: '信息',
}

const ActionListCard: React.FC<Props> = ({ title, actions, context, onActionClick }) => {
  return (
    <div
      style={{
        background: '#fff',
        border: '1px solid #f0f0f0',
        borderRadius: 8,
        padding: '12px 16px',
        marginTop: 8,
      }}
    >
      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 10, color: '#333' }}>
        📋 {title}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {actions.map((action, index) => {
          const config = priorityConfig[action.priority] || priorityConfig.low
          return (
            <div
              key={index}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 10,
                padding: '8px 10px',
                borderRadius: 6,
                background: '#fafafa',
                border: `1px solid ${config.color}20`,
                cursor: action.action_type !== 'none' ? 'pointer' : 'default',
                transition: 'background 0.2s',
              }}
              onClick={() => action.action_type !== 'none' && onActionClick?.(action)}
              onMouseEnter={(e) => {
                if (action.action_type !== 'none') {
                  e.currentTarget.style.background = '#f0f5ff'
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = '#fafafa'
              }}
            >
              {/* 优先级图标 */}
              <div style={{ color: config.color, fontSize: 16, marginTop: 2, flexShrink: 0 }}>
                {config.icon}
              </div>

              {/* 内容 */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                  <Text strong style={{ fontSize: 12, color: '#333' }}>
                    {action.title}
                  </Text>
                </div>
                <Text type="secondary" style={{ fontSize: 11, lineHeight: 1.4 }}>
                  {action.description}
                </Text>
                <div style={{ marginTop: 4 }}>
                  <Space size={4}>
                    <Tag
                      color={config.color}
                      style={{ fontSize: 10, lineHeight: '16px', margin: 0, borderRadius: 3 }}
                    >
                      {config.label}
                    </Tag>
                    <Tag
                      style={{ fontSize: 10, lineHeight: '16px', margin: 0, borderRadius: 3 }}
                    >
                      {categoryLabels[action.category] || action.category}
                    </Tag>
                  </Space>
                </div>
              </div>

              {/* 箭头 */}
              {action.action_type !== 'none' && (
                <div style={{ color: '#bbb', fontSize: 12, marginTop: 4, flexShrink: 0 }}>
                  <RightOutlined />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default ActionListCard
