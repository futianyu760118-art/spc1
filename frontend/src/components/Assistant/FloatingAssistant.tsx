import React, { useEffect, useState } from 'react'
import { Drawer, FloatButton, Badge } from 'antd'
import { RobotOutlined } from '@ant-design/icons'
import ChatPanel from './ChatPanel'
import { useAssistantChat } from './useAssistantChat'

const FloatingAssistant: React.FC = () => {
  const [open, setOpen] = useState(false)
  const { messages, loading, send, skills, loadSkills, clearMessages, stopStreaming } = useAssistantChat()

  useEffect(() => {
    if (open && skills.length === 0) {
      loadSkills()
    }
  }, [open, skills.length, loadSkills])

  return (
    <>
      <FloatButton
        icon={<RobotOutlined />}
        type="primary"
        tooltip="AI智能助手"
        style={{ right: 24, bottom: 24, width: 48, height: 48 }}
        onClick={() => setOpen(true)}
        badge={{ dot: false }}
      />
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

export default FloatingAssistant
