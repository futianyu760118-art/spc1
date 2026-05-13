import { useEffect, useState, useCallback } from 'react'
import { Table, Input, Button, message, Row, Col, Card, DatePicker } from 'antd'
import {
  SearchOutlined, ReloadOutlined, AccountBookOutlined,
  DollarOutlined, BankOutlined, LeftOutlined, RightOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import zhCN from 'antd/locale/zh_CN'
import { materialApi } from '../../../services/api'

dayjs.locale('zh-cn')

interface SupplierPaymentRow {
  supplier_code: string
  supplier_name: string | null
  invoice_date: string | null
  schedule_month: string | null
  payment_term: string | null
  payment_method: string | null
  total_payable: number | null
  monthly_due: number | null
  payment_month: string | null
}

interface Summary {
  total_payable: number
  total_monthly_due: number
  supplier_count: number
}

const fmt = (v: number | null) => {
  if (v == null) return <span style={{ color: '#cbd5e1' }}>-</span>
  return <span style={{ fontFamily: 'monospace', fontWeight: 500 }}>{v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
}

export default function SupplierPayment() {
  const [data, setData] = useState<SupplierPaymentRow[]>([])
  const [summary, setSummary] = useState<Summary | null>(null)
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [supplier, setSupplier] = useState('')
  const [monthFilter, setMonthFilter] = useState<dayjs.Dayjs | null>(dayjs())
  const [sortBy, setSortBy] = useState<string>('')
  const [sortOrder, setSortOrder] = useState<string>('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const month = (monthFilter || dayjs()).format('YYYY-MM')
      const listParams: Record<string, any> = { page, page_size: pageSize }
      if (month) listParams.payment_month = month
      if (supplier) listParams.supplier_name = supplier
      if (sortBy) { listParams.sort_by = sortBy; listParams.sort_order = sortOrder || 'asc' }

      const sumParams: Record<string, any> = {}
      if (month) sumParams.payment_month = month
      if (supplier) sumParams.supplier_name = supplier

      const [listRes, sumRes]: any[] = await Promise.all([
        materialApi.listSupplierPayment(listParams),
        materialApi.getSupplierPaymentSummary(sumParams),
      ])
      setData(listRes.data?.items || [])
      setTotal(listRes.data?.total || 0)
      setSummary(sumRes.data)
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, supplier, monthFilter, sortBy, sortOrder])

  useEffect(() => { load() }, [load])

  const columns = [
    {
      title: '供应商编码', dataIndex: 'supplier_code', width: 140, fixed: 'left' as const, sorter: true,
      render: (v: string) => <span style={{ fontFamily: 'monospace' }}>{v}</span>,
    },
    {
      title: '供应商', dataIndex: 'supplier_name', width: 240, ellipsis: true, fixed: 'left' as const, sorter: true,
      render: (v: string | null) => v ? <strong>{v}</strong> : <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '到票日期', dataIndex: 'invoice_date', width: 120, sorter: true,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '账期', dataIndex: 'payment_term', width: 120, sorter: true,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '付款方式', dataIndex: 'payment_method', width: 140, sorter: true,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '排款月', dataIndex: 'payment_month', width: 120, sorter: true,
      render: (v: string | null) => {
        if (!v) return <span style={{ color: '#cbd5e1' }}>-</span>
        const d = dayjs(v)
        return d.isValid() ? d.format('YYYY年M月') : v
      },
    },
    {
      title: '总应付金额', dataIndex: 'total_payable', width: 140, align: 'right' as const, sorter: true,
      render: fmt,
    },
    {
      title: '月到期应付金额', dataIndex: 'monthly_due', width: 160, align: 'right' as const, sorter: true,
      render: (v: number | null) => {
        if (v == null) return <span style={{ color: '#cbd5e1' }}>-</span>
        const color = v > 0 ? '#e11d48' : '#16a34a'
        return <span style={{ fontFamily: 'monospace', fontWeight: 500, color }}>{v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
      },
    },
  ]

  return (
    <div>
      {/* 统计卡 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { title: '供应商数', value: summary?.supplier_count ?? '-', icon: <AccountBookOutlined />, color: '#6366f1' },
          { title: '总应付金额', value: summary?.total_payable != null ? `¥${summary.total_payable.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}` : '-', icon: <DollarOutlined />, color: '#e11d48' },
          { title: '月到期应付金额', value: summary?.total_monthly_due != null ? `¥${summary.total_monthly_due.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}` : '-', icon: <BankOutlined />, color: '#f59e0b' },
        ].map((card, i) => (
          <Col flex={1} key={i}>
            <Card size="small" className="card-modern" style={{ padding: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ width: 44, height: 44, borderRadius: 10, background: `${card.color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, color: card.color }}>
                  {card.icon}
                </div>
                <div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}>{card.value}</div>
                  <div style={{ fontSize: 12, color: '#64748b' }}>{card.title}</div>
                </div>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      {/* 筛选栏 */}
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <Input
              prefix={<SearchOutlined />}
              placeholder="搜索供应商"
              value={supplier}
              onChange={e => { setSupplier(e.target.value); setPage(1) }}
              style={{ width: 200 }}
              allowClear
            />
          </Col>
          <Col>
            <Button.Group>
              <Button
                icon={<LeftOutlined />}
                onClick={() => { setMonthFilter((monthFilter || dayjs()).subtract(1, 'month')); setPage(1) }}
                title="上一月"
              />
              <DatePicker
                picker="month"
                placeholder="到票月份"
                value={monthFilter}
                onChange={v => { setMonthFilter(v || dayjs()); setPage(1) }}
                style={{ width: 140 }}
                allowClear={false}
                locale={zhCN.DatePicker}
                format="YYYY年MM月"
              />
              <Button
                icon={<RightOutlined />}
                onClick={() => { setMonthFilter((monthFilter || dayjs()).add(1, 'month')); setPage(1) }}
                title="下一月"
              />
              <Button
                onClick={() => { setMonthFilter(dayjs()); setPage(1) }}
                disabled={!!monthFilter && monthFilter.isSame(dayjs(), 'month')}
              >本月</Button>
            </Button.Group>
          </Col>
          <Col flex="auto" />
          <Col>
            <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          </Col>
        </Row>
        <div style={{ marginTop: 8, fontSize: 12, color: '#64748b' }}>
          数据来源：基于 <code>purchase_invoice</code> 表按 <code>supplier_code</code> 聚合。月到期应付 = 到票日期在所选月份的发票 SUM(remain_payable)；总应付 = 该供应商所有发票 SUM(remain_payable)；排款月 = 到票日期 + 账期天数；仅显示所选到票月有发票的供应商。
        </div>
      </div>

      {/* 表格 */}
      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey="supplier_code"
          dataSource={data}
          columns={columns}
          loading={loading}
          size="small"
          scroll={{ x: 1000 }}
          pagination={{
            current: page,
            pageSize,
            total,
            showTotal: t => `共 ${t} 条`,
            showSizeChanger: true,
          }}
          onChange={(pagination, _tableFilters, sorter: any) => {
            setPage(pagination.current || 1)
            setPageSize(pagination.pageSize || 20)
            const sortField = sorter.field as string | undefined
            const sortDir = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : ''
            setSortBy(sortField || '')
            setSortOrder(sortDir)
          }}
        />
      </div>
    </div>
  )
}
