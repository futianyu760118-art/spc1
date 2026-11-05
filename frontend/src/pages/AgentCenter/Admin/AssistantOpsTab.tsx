import { useEffect, useState } from 'react'
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
  initialPanel?: string
}

export default function AssistantOpsTab({ canConfig, initialPanel = 'overview' }: Props) {
  const [panel, setPanel] = useState(initialPanel)
  const options = canConfig ? PANEL_OPTIONS : PANEL_OPTIONS.filter(item => item.value !== 'config')

  useEffect(() => {
    setPanel(initialPanel)
  }, [initialPanel])

  useEffect(() => {
    if (!canConfig && panel === 'config') setPanel('overview')
  }, [canConfig, panel])

  return (
    <div className="ac-ops-layout">
      <nav className="ac-ops-nav" aria-label="助手运营分区">
        {options.map(item => (
          <button
            key={item.value}
            type="button"
            className={panel === item.value ? 'active' : ''}
            onClick={() => setPanel(item.value)}
          >
            {item.label}
          </button>
        ))}
        <div className="note">统计窗口<br />近 30 天</div>
      </nav>

      <div className="ac-ops-content">
        {panel === 'overview' && (
          <AssistantOverviewPanel days={30} onOpenRuns={() => setPanel('runs')} />
        )}
        {panel === 'runs' && <AssistantRunsPanel days={30} />}
        {panel === 'calls' && <AgentCallsPanel />}
        {panel === 'audit' && <ConversationAuditPanel />}
        {panel === 'config' && canConfig && <AssistantConfigTab />}
      </div>
    </div>
  )
}
