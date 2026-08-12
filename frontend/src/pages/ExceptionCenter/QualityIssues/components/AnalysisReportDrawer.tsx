import { useEffect, useState } from 'react'
import { Drawer, Button, Tag, List, Card, Alert, Progress, Space, Typography, message } from 'antd'
import { ReloadOutlined, CopyOutlined } from '@ant-design/icons'

const { Text, Paragraph } = Typography

export interface QualityAnalysisHighFreqFinding {
  defect_type: string
  count: number
  proportion: string
  note: string
}

export interface QualityAnalysisActionItem {
  title: string
  owner_suggestion?: string | null
  priority: string
  due_suggestion?: string | null
}

export interface QualityAnalysisReportOut {
  summary: string
  high_freq_findings: QualityAnalysisHighFreqFinding[]
  root_causes: string[]
  strategies: string[]
  action_items: QualityAnalysisActionItem[]
  prevention: string[]
  generated_at?: string | null
  provider?: string | null
  data_scope?: { total?: number; filters?: any } | null
}

interface Props {
  open: boolean
  onClose: () => void
  report: QualityAnalysisReportOut | null
  loading: boolean
  error: string | null
  onRerun: () => void
}

const PRIORITY_COLOR: Record<string, string> = {
  '高': 'red',
  '中': 'orange',
  '低': 'blue',
}

function copyActionItems(items: QualityAnalysisActionItem[]) {
  const md = items.map(i => {
    const owner = i.owner_suggestion ? ` （责任人: ${i.owner_suggestion}` : ''
    const due = i.due_suggestion ? ` / 时限: ${i.due_suggestion}` : ''
    const tail = owner || due ? `${owner}${due}）` : ''
    return `- [ ] [${i.priority}] ${i.title}${tail}`
  }).join('\n')
  navigator.clipboard.writeText(md).then(
    () => message.success('已复制行动项到剪贴板'),
    () => message.error('复制失败'),
  )
}

export default function AnalysisReportDrawer({ open, onClose, report, loading, error, onRerun }: Props) {
  const scopeTotal = report?.data_scope?.total
  const generatedAt = report?.generated_at ? new Date(report.generated_at).toLocaleString('zh-CN') : '-'

  // Honest fake progress: stages reflect what the backend is actually doing at each elapsed window.
  // Progress asymptotes toward 90 so it never falsely hits 100% before the real Promise resolves;
  // completion is signaled by the report UI replacing this loading block.
  const [progress, setProgress] = useState(0)
  const [stage, setStage] = useState('正在汇总统计数据…')
  useEffect(() => {
    if (!loading) {
      setProgress(0)
      setStage('正在汇总统计数据…')
      return
    }
    const start = Date.now()
    const timer = window.setInterval(() => {
      const elapsed = (Date.now() - start) / 1000
      if (elapsed < 3) {
        setStage('正在汇总统计数据…')
      } else if (elapsed < 8) {
        setStage('正在提取高频异常样本…')
      } else {
        setStage('AI 正在生成分析报告…（最耗时阶段，约需 15-60 秒）')
      }
      const target = elapsed < 3 ? 15 : elapsed < 8 ? 45 : 90
      setProgress(prev => Math.min(target, prev + (target - prev) * 0.12))
    }, 200)
    return () => window.clearInterval(timer)
  }, [loading])

  return (
    <Drawer
      title="品质异常分析报告"
      placement="right"
      width={720}
      open={open}
      onClose={onClose}
      footer={
        <Space style={{ float: 'right' }}>
          <Button icon={<ReloadOutlined />} onClick={onRerun} loading={loading}>重新分析</Button>
          <Button onClick={onClose}>关闭</Button>
        </Space>
      }
    >
      {loading && (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Progress percent={Math.round(progress)} status="active" />
          <div style={{ marginTop: 16, color: '#64748b', fontSize: 13 }}>{stage}</div>
          <div style={{ marginTop: 8, color: '#94a3b8', fontSize: 12 }}>完成后此处会显示完整报告</div>
        </div>
      )}

      {!loading && error && (
        <Alert
          type="error"
          banner
          message="分析失败"
          description={error}
          action={<Button size="small" onClick={onRerun}>重试</Button>}
        />
      )}

      {!loading && !error && report && (
        <>
          <div style={{ marginBottom: 16, color: '#64748b', fontSize: 12 }}>
            <span>provider: {report.provider || '-'}</span>
            <span style={{ margin: '0 8px' }}>·</span>
            <span>生成时间: {generatedAt}</span>
            <span style={{ margin: '0 8px' }}>·</span>
            <span>数据范围: total={scopeTotal ?? '-'}</span>
          </div>

          <Card title="概述" size="small" style={{ marginBottom: 16 }}>
            <Paragraph>{report.summary}</Paragraph>
          </Card>

          <Card title="高频异常发现" size="small" style={{ marginBottom: 16 }}>
            <List
              dataSource={report.high_freq_findings}
              renderItem={(item) => (
                <List.Item>
                  <Space direction="vertical" style={{ width: '100%' }} size={4}>
                    <Space>
                      <Tag color="red">{item.count}</Tag>
                      <Text strong>{item.defect_type}</Text>
                      <Text type="secondary">占比 {item.proportion}</Text>
                    </Space>
                    <Text type="secondary">{item.note}</Text>
                  </Space>
                </List.Item>
              )}
            />
          </Card>

          <Card title="根因分析" size="small" style={{ marginBottom: 16 }}>
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {report.root_causes.map((c, i) => <li key={i}>{c}</li>)}
            </ul>
          </Card>

          <Card title="解决策略" size="small" style={{ marginBottom: 16 }}>
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {report.strategies.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </Card>

          <Card
            title="行动项"
            size="small"
            style={{ marginBottom: 16 }}
            extra={
              <Button
                size="small"
                icon={<CopyOutlined />}
                onClick={() => copyActionItems(report.action_items)}
                disabled={!report.action_items.length}
              >
                复制全部
              </Button>
            }
          >
            <List
              dataSource={report.action_items}
              renderItem={(item) => (
                <List.Item>
                  <Space direction="vertical" style={{ width: '100%' }} size={4}>
                    <Space>
                      <Tag color={PRIORITY_COLOR[item.priority] || 'default'}>{item.priority}</Tag>
                      <Text strong>{item.title}</Text>
                    </Space>
                    {item.owner_suggestion && <Text type="secondary">建议责任人: {item.owner_suggestion}</Text>}
                    {item.due_suggestion && <Text type="secondary">建议时限: {item.due_suggestion}</Text>}
                  </Space>
                </List.Item>
              )}
            />
          </Card>

          <Card title="预防措施" size="small">
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {report.prevention.map((p, i) => <li key={i}>{p}</li>)}
            </ul>
          </Card>
        </>
      )}

      {!loading && !error && !report && (
        <div style={{ textAlign: 'center', padding: 48, color: '#94a3b8' }}>暂无报告</div>
      )}
    </Drawer>
  )
}