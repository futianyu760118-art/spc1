import { Popover, Slider, Button, Space, Typography } from 'antd'
import { FontSizeOutlined } from '@ant-design/icons'
import { useThemeStore } from '../store/theme'

const { Text } = Typography

const FONT_SIZE_OPTIONS = [
  { label: '小', value: 0.85 },
  { label: '中', value: 1.0 },
  { label: '大', value: 1.15 },
  { label: '超大', value: 1.3 },
]

export default function FontSizeSetting() {
  const { fontSizeScale, setFontSizeScale } = useThemeStore()

  const content = (
    <div style={{ width: 240, padding: '8px 0' }}>
      <div style={{ marginBottom: 16 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>预设大小</Text>
        <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
          {FONT_SIZE_OPTIONS.map((option) => (
            <Button
              key={option.value}
              size="small"
              type={fontSizeScale === option.value ? 'primary' : 'default'}
              onClick={() => setFontSizeScale(option.value)}
              style={{ flex: 1 }}
            >
              {option.label}
            </Button>
          ))}
        </div>
      </div>
      <div>
        <Text type="secondary" style={{ fontSize: 12 }}>自定义缩放: {Math.round(fontSizeScale * 100)}%</Text>
        <Slider
          min={0.7}
          max={1.5}
          step={0.05}
          value={fontSizeScale}
          onChange={setFontSizeScale}
          style={{ marginTop: 8 }}
        />
      </div>
      <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #f0f0f0' }}>
        <Text type="secondary" style={{ fontSize: 11 }}>
          预览效果：这是一段示例文本
        </Text>
      </div>
    </div>
  )

  return (
    <Popover
      content={content}
      trigger="click"
      placement="bottomRight"
      title="字体大小设置"
    >
      <Button
        type="text"
        icon={<FontSizeOutlined />}
        style={{ fontSize: 16, width: 36, height: 36, borderRadius: 10, color: '#64748b' }}
      />
    </Popover>
  )
}
