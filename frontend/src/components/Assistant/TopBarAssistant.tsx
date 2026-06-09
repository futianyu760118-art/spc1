import React, { useEffect, useState } from 'react'
import { Button, Badge, Drawer } from 'antd'
import { StarOutlined, RobotOutlined } from '@ant-design/icons'
import ChatPanel from './ChatPanel'
import { useAssistantChat } from './useAssistantChat'

const TopBarAssistant: React.FC = () => {
  const [open, setOpen] = useState(false)
  const { messages, loading, send, skills, loadSkills, clearMessages, stopStreaming } = useAssistantChat()

  useEffect(() => {
    if (open && skills.length === 0) {
      loadSkills()
    }
  }, [open, skills.length, loadSkills])

  return (
    <>
      <Button
        type="default"
        icon={<StarOutlined style={{ color: '#fbbf24' }} />}
        style={{ 
          backgroundColor: '#fff',
          borderColor: '#93c5fd',
          color: '#3b82f6',
          borderRadius: 8,
          fontWeight: 500,
          fontSize: 14,
          height: 32,
          padding: '0 12px',
          display: 'flex',
          alignItems: 'center',
          gap: 6
        }}
        onClick={() => setOpen(true)}
      >
        AI 全局搜索
      </Button>
      <Drawer
        title={
          <span>
            <RobotOutlined style={{ marginRight: 8 }} />
            AI智能助手
          </span>
        }
        placement="right"
        width={480}
        open={open}
        onClose={() => setOpen(false)}
        styles={{ body: { padding: 0, display: 'flex', flexDirection: 'column', height: '100%' } }}
      >
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%' }}>
          <ChatPanel
            messages={messages}
            loading={loading}
            skills={skills}
            onSend={send}
            onClear={clearMessages}
            onStop={stopStreaming}
          />
        </div>
      </Drawer>
    </>
  )
}

export default TopBarAssistant
