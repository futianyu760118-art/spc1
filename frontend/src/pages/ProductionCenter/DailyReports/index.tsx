import { useEffect, useState, useCallback } from 'react'
import { Table, Tag, Input, Button, Space, Row, Col, DatePicker, Alert } from 'antd'
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons'
import type { Dayjs } from 'dayjs'
import dayjs from 'dayjs'
import { productionApi } from '../../../services/api'

interface DailyReportRow {
  id: number | null
  oa_id: string | null
  oa_detail_id: number | null
  report_date: string | null
  sale_order_no: string | null
  production_order_no: string | null
  specification: string | null
  bom_no: string | null
  material_code: string | null
  process: string | null
  color: string | null
  completed_qty: number | null
  workshop: string | null
  work_hours: number | null
  total_wages: number | null
  data_source: string | null
  erp_updated_at: string | null
}

export default function DailyReports() {
  const [data, setData] = useState<DailyReportRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [workshop, setWorkshop] = useState('')
  const [keyword, setKeyword] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, any> = { page, page_size: pageSize }
      if (dateRange && dateRange[0]) params.report_date_from = dateRange[0].format('YYYY-MM-DD')
      if (dateRange && dateRange[1]) params.report_date_to = dateRange[1].format('YYYY-MM-DD')
      if (workshop) params.workshop = workshop
      if (keyword) params.keyword = keyword
      const res: any = await productionApi.listDailyReports(params)
      setData(res.data.items || [])
      setTotal(res.data.total || 0)
    } catch (e: any) {
      setData([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, dateRange, workshop, keyword])

  useEffect(() => { load() }, [load])

  const handleReset = () => {
    setDateRange(null)
    setWorkshop('')
    setKeyword('')
    setPage(1)
  }

  const columns = [
    {
      title: '日期', dataIndex: 'report_date', width: 100,
      render: (v: string | null) => v ? dayjs(v).format('YYYY-MM-DD') : '-',
    },
    { title: '车间', dataIndex: 'workshop', width: 90, render: (v: string | null) => v || '-' },
    { title: '生产订单号', dataIndex: 'production_order_no', width: 120 },
    { title: '销售订单号', dataIndex: 'sale_order_no', width: 120 },
    { title: '物料编码', dataIndex: 'material_code', width: 120 },
    { title: '明细ID', dataIndex: 'oa_detail_id', width: 120, render: (v: number | null) => v ?? '-' },
    { title: '规格', dataIndex: 'specification', width: 160, ellipsis: true },
    { title: 'BOM', dataIndex: 'bom_no', width: 100 },
    { title: '工序', dataIndex: 'process', width: 80, render: (v: string | null) => v || '-' },
    { title: '颜色', dataIndex: 'color', width: 80, render: (v: string | null) => v || '-' },
    {
      title: '完成数', dataIndex: 'completed_qty', width: 90, align: 'right' as const,
      render: (v: number | null) => v != null ? Number(v).toLocaleString() : '-',
    },
    {
      title: '工时', dataIndex: 'work_hours', width: 80, align: 'right' as const,
      render: (v: number | null) => v != null ? `${Number(v).toFixed(1)}h` : '-',
    },
    {
      title: '工资', dataIndex: 'total_wages', width: 90, align: 'right' as const,
      render: (v: number | null) => v != null ? Number(v).toFixed(2) : '-',
    },
    {
      title: '来源', dataIndex: 'data_source', width: 80,
      render: (v: string | null) => v ? <Tag color={v === 'erp' ? 'blue' : 'default'}>{v}</Tag> : '-',
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <DatePicker.RangePicker
              value={dateRange as any}
              onChange={(range) => { setDateRange(range as [Dayjs | null, Dayjs | null] | null); setPage(1) }}
              placeholder={['开始日期', '结束日期']}
              style={{ width: 240 }}
            />
          </Col>
          <Col>
            <Input
              placeholder="车间"
              value={workshop || undefined}
              onChange={e => { setWorkshop(e.target.value); setPage(1) }}
              allowClear
              style={{ width: 130 }}
            />
          </Col>
          <Col>
            <Input
              prefix={<SearchOutlined />}
              placeholder="生产单/销售单/物料"
              value={keyword || undefined}
              onChange={e => { setKeyword(e.target.value); setPage(1) }}
              allowClear
              style={{ width: 220 }}
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button onClick={handleReset}>重置</Button>
              <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
            </Space>
          </Col>
        </Row>
      </div>

      {total === 0 && !loading && (
        <Alert
          type="info" showIcon
          message="暂无日报数据"
          description="生产日报表由 ERP/OA 同步。请前往「数据集成」配置 production_daily_reports 的同步 SQL 后再触发同步。"
          style={{ marginBottom: 16 }}
        />
      )}

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey={(r) => String(r.id ?? r.oa_id ?? Math.random())}
          dataSource={data}
          columns={columns}
          loading={loading}
          scroll={{ x: 1600 }}
          size="small"
          pagination={{
            total, current: page, pageSize,
            onChange: (p, ps) => { setPage(p); setPageSize(ps) },
            showSizeChanger: true,
            showTotal: t => `共 ${t} 条`,
          }}
        />
      </div>
    </div>
  )
}
