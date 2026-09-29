import { useState } from 'react'
import { PageContainer } from '@ant-design/pro-components'
import { Tabs } from 'antd'
import OverviewTab from './OverviewTab'
import type { MrpTabKey } from './OverviewTab'
import OrderCoverageTab from './OrderCoverageTab'
import RunsTab from './RunsTab'
import SuggestionsTab from './SuggestionsTab'
import ExceptionsTab from './ExceptionsTab'
import ParametersTab from './ParametersTab'

export default function MrpWorkbench() {
  const [activeRunId, setActiveRunId] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState('overview')

  const handleOpenRun = (runId: number) => {
    setActiveRunId(runId)
    setActiveTab('shortage')
  }

  const handleNavigate = (key: MrpTabKey) => setActiveTab(key)

  return (
    <PageContainer
      title="MRP 计划"
      content={'把销售订单翻译成"要不要做/买、做多少、何时动手"的清单：有缺口才有建议，无缺口属正常。'}
    >
      <div className="sc-page">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            { key: 'overview', label: '总览', children: <OverviewTab onNavigate={handleNavigate} /> },
            { key: 'shortage', label: '缺口与建议', children: <SuggestionsTab runId={activeRunId} /> },
            { key: 'order', label: '订单覆盖', children: <OrderCoverageTab /> },
            { key: 'exceptions', label: '例外', children: <ExceptionsTab runId={activeRunId} /> },
            {
              key: 'runs',
              label: '批次与对比',
              children: <RunsTab onOpenRun={handleOpenRun} />,
            },
            { key: 'parameters', label: '参数与替代', children: <ParametersTab /> },
          ]}
        />
      </div>
    </PageContainer>
  )
}
