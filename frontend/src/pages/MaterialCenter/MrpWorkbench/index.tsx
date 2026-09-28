import { useState } from 'react'
import { PageContainer } from '@ant-design/pro-components'
import { Tabs } from 'antd'
import RunsTab from './RunsTab'
import SuggestionsTab from './SuggestionsTab'
import MaterialBalanceTab from './MaterialBalanceTab'
import ComparisonTab from './ComparisonTab'
import ParametersTab from './ParametersTab'

export default function MrpWorkbench() {
  const [activeRunId, setActiveRunId] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState('runs')

  const handleOpenRun = (runId: number) => {
    setActiveRunId(runId)
    setActiveTab('balance')
  }

  return (
    <PageContainer title="MRP 运算">
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          { key: 'runs', label: '运算批次', children: <RunsTab onOpenRun={handleOpenRun} /> },
          { key: 'suggestions', label: '计划建议', children: <SuggestionsTab runId={activeRunId} /> },
          { key: 'balance', label: '物料平衡', children: <MaterialBalanceTab runId={activeRunId} /> },
          { key: 'comparison', label: 'K3 对比', children: <ComparisonTab runId={activeRunId} /> },
          { key: 'parameters', label: '参数维护', children: <ParametersTab /> },
        ]}
      />
    </PageContainer>
  )
}
