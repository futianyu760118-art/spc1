import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Divider,
  Empty,
  Input,
  Modal,
  Row,
  Segmented,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  TreeSelect,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useSearchParams } from 'react-router-dom'
import { monthlyCapacityPlanApi } from '../../services/monthlyCapacityPlan'
import { useAuthStore } from '../../store/auth'

interface WeekRow {
  order_no: string
  line_no: string
  product_code?: string
  product_name?: string
  bom_no?: string
  stage: string
  stage_label: string
  quantity: number
  manpower: number
  daily_work_hours: number
  hours: number
  status: string
  remark?: string
  continued_from_prev_week: boolean
}

interface WeekDay {
  date: string
  weekday: string
  order_count: number
  line_count: number
  total_qty: number
  rows: WeekRow[]
}

interface WeekData {
  week_start: string
  week_end: string
  generated_at: string
  has_plan: boolean
  snapshot_id?: number
  snapshot_no?: string
  snapshot_status?: string
  published_at?: string
  summary: {
    order_count: number
    line_count: number
    total_qty: number
    stage_hours: Record<string, number>
  }
  days: WeekDay[]
}

interface WeeklyRecipient {
  id: number
  user_id: number
  username: string
  display_name: string
  category?: string
  enabled: boolean
  wecom_user_id?: string
  remark?: string
}

interface OrgOption {
  id: number
  name: string
  parent_id?: number | null
}

interface RoleOption {
  value: string
  label: string
}

interface RecipientCandidate {
  user_id: number
  username: string
  display_name: string
  role_code?: string
  role_name?: string
  org_id?: number | null
  org_name?: string | null
  position_name?: string | null
  wecom_user_id?: string | null
  is_recipient: boolean
  enabled: boolean
}

interface OrgTreeNode {
  title: string
  value: number
  children?: OrgTreeNode[]
}

function buildOrgTree(orgs: OrgOption[]): OrgTreeNode[] {
  const nodes = new Map<number, OrgTreeNode>()
  orgs.forEach((org) => nodes.set(org.id, { title: org.name, value: org.id, children: [] }))
  const roots: OrgTreeNode[] = []
  orgs.forEach((org) => {
    const node = nodes.get(org.id)!
    const parent = org.parent_id ? nodes.get(org.parent_id) : null
    if (parent) parent.children!.push(node)
    else roots.push(node)
  })
  const clean = (node: OrgTreeNode): OrgTreeNode =>
    node.children && node.children.length
      ? { ...node, children: node.children.map(clean) }
      : { title: node.title, value: node.value }
  return roots.map(clean)
}

const STAGE_OPTIONS = [
  { label: '全部', value: 'all' },
  { label: '组装', value: 'assembly' },
  { label: '包装', value: 'packaging' },
]

function formatNumber(value?: number | null) {
  return Number(value || 0).toLocaleString('zh-CN')
}

function statusTag(status: string) {
  if (status === 'risk') return <Tag color="red">超负荷</Tag>
  if (status === 'warn') return <Tag color="orange">注意</Tag>
  return <Tag color="green">正常</Tag>
}

export default function WeeklyCapacity() {
  const [searchParams] = useSearchParams()
  const weekStart = searchParams.get('week_start') || undefined
  const snapshotId = searchParams.get('snapshot_id') || undefined
  const hasPermission = useAuthStore((state) => state.hasPermission)
  const canManage = hasPermission('production.monthly_capacity_plan', 'manage')
  const [data, setData] = useState<WeekData | null>(null)
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [pushing, setPushing] = useState(false)
  const [selectedDate, setSelectedDate] = useState('')
  const [stage, setStage] = useState('all')
  const [keyword, setKeyword] = useState('')
  const [recipientsOpen, setRecipientsOpen] = useState(false)
  const [recipientsLoading, setRecipientsLoading] = useState(false)
  const [savingRecipients, setSavingRecipients] = useState(false)
  const [recipients, setRecipients] = useState<WeeklyRecipient[]>([])
  const [orgOptions, setOrgOptions] = useState<OrgOption[]>([])
  const [roleOptions, setRoleOptions] = useState<RoleOption[]>([])
  const [candidateOrg, setCandidateOrg] = useState<number | undefined>()
  const [candidateRole, setCandidateRole] = useState<string | undefined>()
  const [candidateKeyword, setCandidateKeyword] = useState('')
  const [candidates, setCandidates] = useState<RecipientCandidate[]>([])
  const [candidatesLoading, setCandidatesLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = snapshotId
        ? await monthlyCapacityPlanApi.getWeeklySnapshot(Number(snapshotId))
        : await monthlyCapacityPlanApi.getWeeklyCapacity({ week_start: weekStart })
      setData(res.data || null)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [snapshotId, weekStart])

  useEffect(() => {
    load()
  }, [load])

  const generateSnapshot = async () => {
    setGenerating(true)
    try {
      const res: any = await monthlyCapacityPlanApi.generateWeeklySnapshot({
        week_start: weekStart,
      })
      setData(res.data || null)
      setSelectedDate('')
      message.success(`已生成快照 ${res.data?.snapshot_no || ''}`)
    } catch {
      // 全局拦截器提示
    } finally {
      setGenerating(false)
    }
  }

  const loadCandidates = async (params?: {
    org_id?: number
    role_code?: string
    keyword?: string
  }) => {
    setCandidatesLoading(true)
    try {
      const res: any = await monthlyCapacityPlanApi.listWeeklyRecipientCandidates({
        org_id: params?.org_id ?? candidateOrg,
        role_code: params?.role_code ?? candidateRole,
        keyword: params?.keyword ?? candidateKeyword,
        limit: 500,
      })
      setCandidates(res.data || [])
    } catch {
      setCandidates([])
    } finally {
      setCandidatesLoading(false)
    }
  }

  const openRecipients = async () => {
    setRecipientsOpen(true)
    setRecipientsLoading(true)
    try {
      const [recipientRes, optionRes, candidateRes] = await Promise.all([
        monthlyCapacityPlanApi.listWeeklyRecipients(),
        monthlyCapacityPlanApi.listWeeklyRecipientOptions(),
        monthlyCapacityPlanApi.listWeeklyRecipientCandidates({ limit: 500 }),
      ])
      setRecipients((recipientRes as any).data || [])
      setOrgOptions((optionRes as any).data?.orgs || [])
      setRoleOptions((optionRes as any).data?.roles || [])
      setCandidates((candidateRes as any).data || [])
    } catch {
      setRecipients([])
    } finally {
      setRecipientsLoading(false)
    }
  }

  const addCandidate = (candidate: RecipientCandidate) => {
    if (recipients.some((item) => item.user_id === candidate.user_id)) return
    setRecipients((prev) => [
      ...prev,
      {
        id: -candidate.user_id,
        user_id: candidate.user_id,
        username: candidate.username,
        display_name: candidate.display_name,
        category: candidate.role_name,
        enabled: true,
        wecom_user_id: candidate.wecom_user_id || undefined,
      },
    ])
    setCandidates((prev) =>
      prev.map((item) =>
        item.user_id === candidate.user_id
          ? { ...item, is_recipient: true, enabled: true }
          : item,
      ),
    )
  }

  const saveRecipients = async () => {
    setSavingRecipients(true)
    try {
      const res: any = await monthlyCapacityPlanApi.updateWeeklyRecipients(
        recipients.map((item) => ({
          id: item.id > 0 ? item.id : undefined,
          user_id: item.user_id,
          enabled: item.enabled,
          category: item.category,
        })),
      )
      setRecipients(res.data || [])
      setRecipientsOpen(false)
      message.success('收件人配置已保存')
    } catch {
      // 全局拦截器提示
    } finally {
      setSavingRecipients(false)
    }
  }

  const pushToWecom = () => {
    if (!data?.has_plan) {
      message.warning('下周暂无排产计划，不能推送')
      return
    }
    Modal.confirm({
      title: '确认推送企业微信？',
      content: '将按当前收件人配置发送给已启用的收件人，发送后车间可在企业微信查看。',
      okText: '确认推送',
      cancelText: '取消',
      onOk: async () => {
        setPushing(true)
        try {
          let targetId = data.snapshot_id
          if (!targetId) {
            const generated: any = await monthlyCapacityPlanApi.generateWeeklySnapshot({
              week_start: weekStart,
            })
            setData(generated.data || null)
            targetId = generated.data?.snapshot_id
          }
          if (!targetId) {
            message.warning('快照生成失败，请重试')
            return
          }
          const res: any = await monthlyCapacityPlanApi.publishWeeklySnapshot(Number(targetId))
          const result = res.data || {}
          if (result.success) {
            setData((prev) => prev ? {
              ...prev,
              snapshot_no: result.snapshot_no || prev.snapshot_no,
              snapshot_status: 'published',
              published_at: result.published_at,
            } : prev)
            message.success(`已推送 ${result.recipients?.length || 0} 人`)
          } else {
            message.error(result.error || '企业微信推送失败')
          }
        } catch {
          // 全局拦截器提示
        } finally {
          setPushing(false)
        }
      },
    })
  }

  useEffect(() => {
    if (!data?.days?.length) return
    if (!data.days.some((day) => day.date === selectedDate)) {
      const firstWithRows = data.days.find((day) => day.rows.length > 0)
      setSelectedDate(firstWithRows?.date || data.days[0].date)
    }
  }, [data, selectedDate])

  const selectedDay = data?.days.find((day) => day.date === selectedDate)
  const maxDayQty = useMemo(
    () => Math.max(1, ...(data?.days || []).map((day) => day.total_qty)),
    [data],
  )
  const orgTreeData = useMemo(() => buildOrgTree(orgOptions), [orgOptions])

  const filteredRows = useMemo(() => {
    const rows = selectedDay?.rows || []
    const lowered = keyword.trim().toLowerCase()
    return rows.filter((row) => {
      if (stage !== 'all' && row.stage !== stage) return false
      if (!lowered) return true
      return [row.order_no, row.product_code, row.product_name, row.bom_no]
        .join(' ')
        .toLowerCase()
        .includes(lowered)
    })
  }, [selectedDay, stage, keyword])

  const printWeeklyRows = (title: string, days: WeekDay[]) => {
    const escape = (value: unknown) =>
      String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
    const statusText = (status: string) =>
      status === 'risk' ? '超负荷' : status === 'warn' ? '注意' : '正常'
    const rowsHtml = (date: string, rows: WeekRow[]) =>
      rows.map((row) => `<tr>
        <td>${date.slice(5)}</td>
        <td>${escape(row.order_no)}</td>
        <td>${escape(row.line_no)}</td>
        <td>${escape(row.product_code)}</td>
        <td>${escape(row.product_name)}</td>
        <td>${escape(row.bom_no)}</td>
        <td>${escape(row.stage_label)}</td>
        <td class="num">${row.quantity}</td>
        <td class="num">${row.manpower}</td>
        <td class="num">${row.daily_work_hours}h</td>
        <td>${escape(statusText(row.status))}${row.continued_from_prev_week ? '（延续）' : ''}</td>
        <td>${escape(row.remark)}</td>
      </tr>`).join('')
    const daysHtml = days.map((day) => `
      <section>
        <h2>${escape(day.date)} ${escape(day.weekday)}</h2>
        ${day.rows.length ? `<table>
          <thead><tr><th>日期</th><th>订单号</th><th>行号</th><th>产品编码</th><th>产品名称</th><th>BOM</th><th>工序</th><th class="num">数量</th><th class="num">人数</th><th class="num">日工时</th><th>状态</th><th>备注</th></tr></thead>
          <tbody>${rowsHtml(day.date, day.rows)}</tbody>
        </table>` : '<div class="empty">当日无排产</div>'}
      </section>`).join('')
    const summary = data?.summary
    const html = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8" />
      <title>${escape(title)}</title>
      <style>
        @page { size: A4 landscape; margin: 8mm; }
        body { font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif; color: #1f2329; font-size: 10px; margin: 0; }
        h1 { font-size: 16px; margin: 0 0 4px; }
        h2 { font-size: 11px; margin: 12px 0 5px; padding-bottom: 3px; border-bottom: 1px solid #ddd; }
        .meta { color: #666; font-size: 9px; margin-bottom: 8px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { border: 1px solid #cfcfcf; padding: 3px 4px; text-align: left; vertical-align: top; }
        th { background: #f5f5f5; font-weight: 600; }
        .num { text-align: right; white-space: nowrap; }
        section { break-inside: avoid; }
        .empty { color: #999; padding: 6px 0; }
      </style></head><body>
      <h1>${escape(title)}</h1>
      <div class="meta">周期 ${escape(data?.week_start)} ~ ${escape(data?.week_end)}
        ｜ 快照 ${escape(data?.snapshot_no || '-')}
        ｜ 订单 ${summary?.order_count || 0} 个 / 明细 ${summary?.line_count || 0} 行 / 数量 ${summary?.total_qty || 0} 件
      </div>
      ${daysHtml}
      </body></html>`
    const printWindow = window.open('', '_blank', 'width=1200,height=800')
    if (!printWindow) {
      message.warning('浏览器阻止了打印窗口，请允许弹窗后重试')
      return
    }
    printWindow.document.write(html)
    printWindow.document.close()
    printWindow.focus()
    setTimeout(() => printWindow.print(), 300)
  }

  const printCurrentDay = () => {
    if (!data || !selectedDay) {
      message.warning('暂无可打印的排产数据')
      return
    }
    printWeeklyRows(
      `下周排产计划 ${selectedDay.date} ${selectedDay.weekday}`,
      [{ ...selectedDay, rows: filteredRows }],
    )
  }

  const printWholeWeek = () => {
    if (!data) {
      message.warning('暂无可打印的排产数据')
      return
    }
    printWeeklyRows(`下周排产计划 ${data.week_start} ~ ${data.week_end}`, data.days)
  }

  const columns: ColumnsType<WeekRow> = [
    { title: '日期', width: 90, render: () => selectedDay?.date.slice(5) || '-' },
    { title: '订单号', dataIndex: 'order_no', width: 170 },
    { title: '行号', dataIndex: 'line_no', width: 60 },
    { title: '产品编码', dataIndex: 'product_code', width: 170, ellipsis: true },
    { title: '产品名称', dataIndex: 'product_name', width: 200, ellipsis: true },
    { title: 'BOM', dataIndex: 'bom_no', width: 180, ellipsis: true },
    {
      title: '工序',
      dataIndex: 'stage_label',
      width: 70,
      render: (value: string) => (
        <Tag color={value === '组装' ? 'blue' : 'green'}>{value}</Tag>
      ),
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      width: 80,
      align: 'right',
      render: (value: number) => formatNumber(value),
    },
    { title: '人数', dataIndex: 'manpower', width: 60, align: 'right' },
    {
      title: '日工时',
      dataIndex: 'daily_work_hours',
      width: 80,
      align: 'right',
      render: (value: number) => `${value}h`,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string, row) => (
        <span>
          {statusTag(value)}
          {row.continued_from_prev_week && <Tag>延续</Tag>}
        </span>
      ),
    },
    { title: '备注', dataIndex: 'remark', width: 160, render: (value?: string) => value || '-' },
  ]

  if (loading && !data) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 80 }}>
        <Spin size="large" tip="加载下周产能计划..." />
      </div>
    )
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f3f5f8', padding: 12 }}>
      <div style={{ maxWidth: 1440, margin: '0 auto' }}>
        <Card
          title="下周排产计划"
          extra={
            <Space wrap>
              {canManage && (
                <Button loading={generating} onClick={generateSnapshot}>
                  生成快照
                </Button>
              )}
              {canManage && (
                <Button type="primary" loading={pushing} onClick={pushToWecom}>
                  推送企业微信
                </Button>
              )}
              {canManage && <Button onClick={openRecipients}>收件人配置</Button>}
              <Button disabled={!data} onClick={printCurrentDay}>打印当前日</Button>
              <Button disabled={!data} onClick={printWholeWeek}>打印本周</Button>
              <Tag color="blue">只读</Tag>
            </Space>
          }
          styles={{ body: { padding: 16 } }}
        >
          {data ? (
            <>
              <div style={{ color: '#595959', marginBottom: 12 }}>
                周期 <b>{data.week_start}</b> ~ <b>{data.week_end}</b>
                {data.snapshot_no && (
                  <span style={{ marginLeft: 12, color: '#8c8c8c' }}>
                    快照 {data.snapshot_no}
                  </span>
                )}
                {data.published_at && (
                  <span style={{ marginLeft: 12, color: '#8c8c8c' }}>
                    发布时间 {data.published_at.replace('T', ' ').slice(0, 19)}
                  </span>
                )}
                {!data.snapshot_no && (
                  <span style={{ marginLeft: 12, color: '#8c8c8c' }}>
                    生成时间 {data.generated_at?.replace('T', ' ')}
                  </span>
                )}
              </div>

              {!data.has_plan && (
                <Alert
                  type="warning"
                  showIcon
                  message="下周暂无排产计划"
                  description="请先在「新排产方案」中生成并激活下周计划后再推送。"
                  style={{ marginBottom: 12 }}
                />
              )}

              <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
                <Col xs={12} md={4}>
                  <Statistic title="订单数" value={data.summary.order_count} />
                </Col>
                <Col xs={12} md={4}>
                  <Statistic title="订单行数" value={data.summary.line_count} />
                </Col>
                <Col xs={12} md={4}>
                  <Statistic
                    title="总数量"
                    value={data.summary.total_qty}
                    formatter={(value) => formatNumber(Number(value))}
                  />
                </Col>
                <Col xs={12} md={4}>
                  <Statistic
                    title="组装人时"
                    value={data.summary.stage_hours.assembly || 0}
                    precision={1}
                  />
                </Col>
                <Col xs={12} md={4}>
                  <Statistic
                    title="包装人时"
                    value={data.summary.stage_hours.packaging || 0}
                    precision={1}
                  />
                </Col>
              </Row>

              <div style={{ fontWeight: 600, marginBottom: 8 }}>每日排产负荷</div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))',
                  gap: 8,
                  marginBottom: 16,
                }}
              >
                {data.days.map((day) => {
                  const active = day.date === selectedDate
                  const pct = day.total_qty > 0
                    ? Math.max(3, Math.round((day.total_qty / maxDayQty) * 100))
                    : 0
                  return (
                    <button
                      key={day.date}
                      type="button"
                      onClick={() => setSelectedDate(day.date)}
                      style={{
                        textAlign: 'left',
                        border: `1px solid ${active ? '#1677ff' : '#e8e8e8'}`,
                        background: active ? '#f0f7ff' : '#fff',
                        borderRadius: 4,
                        padding: '8px 9px',
                        cursor: 'pointer',
                      }}
                    >
                      <div style={{ color: '#8c8c8c', fontSize: 11 }}>{day.weekday}</div>
                      <div style={{ fontWeight: 700, fontSize: 13 }}>{day.date.slice(5)}</div>
                      <div style={{ height: 4, background: '#f0f0f0', borderRadius: 2, margin: '7px 0 5px' }}>
                        <div style={{ width: `${pct}%`, height: '100%', background: '#1677ff', borderRadius: 2 }} />
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', color: '#8c8c8c', fontSize: 10 }}>
                        <span>{formatNumber(day.total_qty)} 件</span>
                        <span>{day.line_count} 行</span>
                      </div>
                    </button>
                  )
                })}
              </div>

              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: 12,
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 10,
                }}
              >
                <Segmented
                  options={STAGE_OPTIONS}
                  value={stage}
                  onChange={(value) => setStage(String(value))}
                />
                <Input.Search
                  allowClear
                  placeholder="订单号 / 产品 / BOM"
                  style={{ width: 260, maxWidth: '100%' }}
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                />
              </div>

              <div style={{ color: '#8c8c8c', fontSize: 12, marginBottom: 8 }}>
                <b>{selectedDay?.date || '-'}</b>
                {selectedDay ? ` ${selectedDay.weekday}` : ''}
                <span style={{ marginLeft: 10 }}>当日订单 {selectedDay?.order_count || 0} 个</span>
                <span style={{ marginLeft: 10 }}>明细 {selectedDay?.line_count || 0} 行</span>
                <span style={{ marginLeft: 10 }}>数量 {formatNumber(selectedDay?.total_qty)} 件</span>
                <span style={{ marginLeft: 10 }}>当前筛选 {filteredRows.length} 行</span>
              </div>

              <Table<WeekRow>
                rowKey={(row) => `${row.order_no}-${row.line_no}-${row.stage}`}
                size="small"
                bordered
                columns={columns}
                dataSource={filteredRows}
                pagination={{ pageSize: 50, showSizeChanger: false }}
                scroll={{ x: 1320 }}
                locale={{ emptyText: <Empty description="当日无排产" /> }}
              />
            </>
          ) : (
            <Empty description="暂无下周排产数据" />
          )}
        </Card>

        <Modal
          title="推送收件人配置"
          open={recipientsOpen}
          onCancel={() => setRecipientsOpen(false)}
          onOk={saveRecipients}
          okText="保存"
          confirmLoading={savingRecipients}
          width={820}
        >
          {recipientsLoading ? (
            <div style={{ padding: 24, textAlign: 'center' }}>
              <Spin />
            </div>
          ) : (
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                <div style={{ fontWeight: 600 }}>已配置收件人（{recipients.length} 人）</div>
                <Checkbox
                  checked={recipients.length > 0 && recipients.every((item) => item.enabled)}
                  indeterminate={
                    recipients.some((item) => item.enabled) &&
                    !recipients.every((item) => item.enabled)
                  }
                  onChange={(event) =>
                    setRecipients((prev) =>
                      prev.map((item) => ({ ...item, enabled: event.target.checked })),
                    )
                  }
                >
                  全选 / 取消全选
                </Checkbox>
              </div>
              <div style={{ display: 'grid', gap: 8, maxHeight: 220, overflowY: 'auto', paddingRight: 4 }}>
                {recipients.map((item) => (
                  <Checkbox
                    key={item.id}
                    checked={item.enabled}
                    onChange={(event) =>
                      setRecipients((prev) =>
                        prev.map((row) =>
                          row.id === item.id ? { ...row, enabled: event.target.checked } : row,
                        ),
                      )
                    }
                  >
                    <span style={{ fontWeight: 600 }}>{item.display_name}</span>
                    <span style={{ marginLeft: 8, color: '#8c8c8c' }}>{item.category || '-'}</span>
                    {!item.wecom_user_id && (
                      <Tag color="orange" style={{ marginLeft: 8 }}>
                        未绑定企微
                      </Tag>
                    )}
                  </Checkbox>
                ))}
              </div>

              <Divider style={{ margin: '4px 0' }}>新增人员（按组织 / 角色选择）</Divider>
              <Space wrap>
                <TreeSelect
                  allowClear
                  treeDefaultExpandAll
                  placeholder="按组织选择"
                  style={{ width: 220 }}
                  value={candidateOrg}
                  treeData={orgTreeData}
                  onChange={(value) => {
                    const next = value ? Number(value) : undefined
                    setCandidateOrg(next)
                    loadCandidates({ org_id: next })
                  }}
                />
                <Select
                  allowClear
                  placeholder="按角色选择"
                  style={{ width: 220 }}
                  value={candidateRole}
                  options={roleOptions}
                  onChange={(value) => {
                    setCandidateRole(value)
                    loadCandidates({ role_code: value })
                  }}
                />
                <Input.Search
                  allowClear
                  placeholder="姓名 / 工号 / 账号"
                  style={{ width: 240 }}
                  value={candidateKeyword}
                  onChange={(event) => setCandidateKeyword(event.target.value)}
                  onSearch={(value) => loadCandidates({ keyword: value })}
                />
              </Space>

              <div style={{ maxHeight: 220, overflowY: 'auto', border: '1px solid #f0f0f0', borderRadius: 4, padding: 8 }}>
                {candidatesLoading ? (
                  <div style={{ textAlign: 'center', padding: 16 }}>
                    <Spin size="small" />
                  </div>
                ) : candidates.length ? (
                  <Space direction="vertical" size={6} style={{ width: '100%' }}>
                    {candidates.map((candidate) => (
                      <div
                        key={candidate.user_id}
                        style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}
                      >
                        <div style={{ minWidth: 0 }}>
                          <span style={{ fontWeight: 600 }}>{candidate.display_name}</span>
                          <span style={{ marginLeft: 8, color: '#8c8c8c', fontSize: 12 }}>
                            {[candidate.org_name, candidate.role_name, candidate.position_name].filter(Boolean).join(' / ') || '-'}
                          </span>
                          {!candidate.wecom_user_id && (
                            <Tag color="orange" style={{ marginLeft: 8 }}>
                              未绑定企微
                            </Tag>
                          )}
                        </div>
                        {candidate.is_recipient ? (
                          <Tag color="blue">已在名单</Tag>
                        ) : (
                          <Button
                            size="small"
                            disabled={!candidate.wecom_user_id}
                            onClick={() => addCandidate(candidate)}
                          >
                            添加
                          </Button>
                        )}
                      </div>
                    ))}
                  </Space>
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配人员" />
                )}
              </div>
            </Space>
          )}
        </Modal>
      </div>
    </div>
  )
}

