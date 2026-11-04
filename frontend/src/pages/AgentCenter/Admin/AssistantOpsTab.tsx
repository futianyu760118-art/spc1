import { useState } from 'react'
import { Segmented } from 'antd'
import {
  AgentCallsPanel, AssistantOverviewPanel, AssistantRunsPanel, ConversationAuditPanel,
} from './AssistantOpsPanels'
import AssistantConfigTab from './AssistantConfigTab'

const PANEL_OPTIONS = [
  { value: 'overview', label: '概览' },
  { value: 'runs', label: '运行记录' },
  { value: 'calls', label: '调用审计' },
  { value: 'audit', label: '会话审计' },
  { value: 'config', label: '助手配置' },
]

interface Props {
  canConfig: boolean
}

export default function AssistantOpsTab({ canConfig }: Props) {
  const [panel, setPanel] = useState('overview')
  const options = canConfig ? PANEL_OPTIONS : PANEL_OPTIONS.filter(item => item.value !== 'config')

  return (
    <div>
      <div className="ai-ops-bar">
        <Segmented
          value={panel}
          options={options}
          onChange={value => setPanel(String(value))}
        />
      </div>
      <div className="ai-ops-panels">
        {panel === 'overview' && <AssistantOverviewPanel days={30} />}
        {panel === 'runs' && <AssistantRunsPanel days={30} />}
        {panel === 'calls' && <AgentCallsPanel />}
        {panel === 'audit' && <ConversationAuditPanel />}
        {panel === 'config' && canConfig && <AssistantConfigTab />}
      </div>
    </div>
  )
}
