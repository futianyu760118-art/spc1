import React from 'react'
import { Button, Input } from 'antd'
import { PauseCircleOutlined, SendOutlined } from '@ant-design/icons'

interface Props {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  loading: boolean
  disabled?: boolean
  placeholder?: string
  inputRef?: React.RefObject<any>
  onStop?: () => void
}

export default function ChatComposer({
  value, onChange, onSend, loading, disabled, placeholder, inputRef, onStop,
}: Props) {
  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      onSend()
    }
  }

  return (
    <div className="ai-composer">
      <div className="ai-composer-box">
        <Input.TextArea
          ref={inputRef}
          value={value}
          onChange={event => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          variant="borderless"
          autoSize={{ minRows: 1, maxRows: 4 }}
          disabled={disabled || loading}
          style={{ flex: 1, padding: '4px 0', resize: 'none' }}
        />
        {loading && onStop ? (
          <Button
            shape="circle"
            icon={<PauseCircleOutlined />}
            onClick={onStop}
            danger
            title="停止生成"
          />
        ) : (
          <Button
            type="primary"
            shape="circle"
            icon={<SendOutlined />}
            onClick={onSend}
            disabled={!value.trim() || disabled}
            title="发送"
          />
        )}
      </div>
      <div className="ai-composer-hint">Enter 发送 · Shift+Enter 换行</div>
    </div>
  )
}
