import React from 'react'
import { Button, Input, message } from 'antd'
import { PaperClipOutlined, PauseCircleOutlined, SendOutlined } from '@ant-design/icons'

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
          className="ai-composer-input"
          value={value}
          onChange={event => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          variant="borderless"
          autoSize={{ minRows: 2, maxRows: 4 }}
          disabled={disabled || loading}
        />
        <div className="ai-composer-tools">
          <Button
            type="text"
            size="small"
            className="ai-attach-btn"
            icon={<PaperClipOutlined />}
            title="附件功能暂未开放"
            onClick={() => message.info('附件功能暂未开放')}
          />
          <span className="ai-composer-tip">Enter 发送 · Shift + Enter 换行</span>
          {loading && onStop ? (
            <Button danger icon={<PauseCircleOutlined />} onClick={onStop} title="停止生成">
              停止
            </Button>
          ) : (
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={onSend}
              disabled={disabled}
              title="发送"
            >
              发送
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
