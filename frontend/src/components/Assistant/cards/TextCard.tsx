import React from 'react'
import { Card } from 'antd'

interface Props {
  title: string
  payload: { content: string }
}

const TextCard: React.FC<Props> = ({ title, payload }) => {
  return (
    <Card size="small" title={title} style={{ marginBottom: 8 }}>
      <div style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>
        {payload?.content || ''}
      </div>
    </Card>
  )
}

export default TextCard
