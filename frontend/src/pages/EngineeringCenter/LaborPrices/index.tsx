import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Input,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { engineeringApi } from '../../../services/engineering'
import { useAuthStore } from '../../../store/auth'

interface LaborPriceRow {
  id: number
  bom_code?: string
  product_code?: string
  product_name?: string
  process_type?: string
  workshop_name?: string
  price?: number
  oa_pph?: number
  bottleneck_hours?: number
  standard_capacity?: number
  manpower?: number
  remark?: string
  oa_main_id?: string
  source?: string
  last_sync_time?: string
}

const PROCESS_OPTIONS = ['组装', '组装前加工', '包装', '包装前加工'].map((value) => ({
  value,
  label: value,
}))

export default function LaborPrices() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const orderNo = searchParams.get('orderNo') || ''
  const lineNo = searchParams.get('lineNo') || ''
  const bomNo = searchParams.get('bomNo') || ''
  const productCode = searchParams.get('productCode') || ''

  const [keyword, setKeyword] = useState(bomNo || productCode || '')
  const [processType, setProcessType] = useState<string | undefined>()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [rows, setRows] = useState<LaborPriceRow[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await engineeringApi.listLaborPrices({
        page,
        page_size: pageSize,
        keyword: keyword.trim() || undefined,
        process_type: processType,
      })
      setRows(res.data?.items || [])
      setTotal(res.data?.total || 0)
    } catch {
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [keyword, page, pageSize, processType])

  useEffect(() => {
    setKeyword(bomNo || productCode || '')
    setPage(1)
  }, [bomNo, productCode])

  useEffect(() => {
    load()
  }, [load])

  const columns: ColumnsType<LaborPriceRow> = [
    {
      title: 'BOM',
      dataIndex: 'bom_code',
      width: 220,
      ellipsis: true,
      render: (value?: string) => value || '-',
    },
    {
      title: '产品编码',
      dataIndex: 'product_code',
      width: 200,
      ellipsis: true,
      render: (value?: string) => value || '-',
    },
    {
      title: '产品名称',
      dataIndex: 'product_name',
      width: 180,
      ellipsis: true,
      render: (value?: string) => value || '-',
    },
    {
      title: '工序',
      dataIndex: 'process_type',
      width: 110,
      render: (value?: string) => <Tag>{value || '-'}</Tag>,
    },
    {
      title: '车间',
      dataIndex: 'workshop_name',
      width: 120,
      render: (value?: string) => value || '-',
    },
    {
      title: 'PPH',
      dataIndex: 'oa_pph',
      width: 90,
      align: 'right',
      render: (value?: number) => (value === null || value === undefined ? '-' : value),
    },
    {
      title: '瓶颈工时',
      dataIndex: 'bottleneck_hours',
      width: 100,
      align: 'right',
      render: (value?: number) => (value === null || value === undefined ? '-' : value),
    },
    {
      title: '标准产能',
      dataIndex: 'standard_capacity',
      width: 100,
      align: 'right',
      render: (value?: number) => (value === null || value === undefined ? '-' : value),
    },
    {
      title: '单价',
      dataIndex: 'price',
      width: 100,
      align: 'right',
      render: (value?: number) => (value === null || value === undefined ? '-' : value),
    },
    {
      title: '人数',
      dataIndex: 'manpower',
      width: 80,
      align: 'right',
      render: (value?: number) => (value === null || value === undefined ? '-' : value),
    },
    {
      title: '备注',
      dataIndex: 'remark',
      width: 160,
      ellipsis: true,
      render: (value?: string) => value || '-',
    },
    {
      title: 'OA 主表',
      dataIndex: 'oa_main_id',
      width: 100,
      render: (value?: string) => value || '-',
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 80,
      render: (value?: string) => <Tag color={value === 'OA' ? 'blue' : 'default'}>{value || '-'}</Tag>,
    },
    {
      title: '同步时间',
      dataIndex: 'last_sync_time',
      width: 160,
      render: (value?: string) =>
        value ? (
          <Tooltip title={dayjs(value).format('YYYY-MM-DD HH:mm:ss')}>
            {dayjs(value).format('MM-DD HH:mm')}
          </Tooltip>
        ) : (
          '-'
        ),
    },
  ]

  const goMainSystem = () => {
    const auth = useAuthStore.getState()
    if (auth.hasPermission('dashboard', 'read')) {
      navigate('/dashboard')
      return
    }
    if (auth.hasPermission('production.schedule_plans', 'read')) {
      navigate('/todo-workbench')
      return
    }
    if (auth.hasPermission('orders.list', 'read')) {
      navigate('/orders')
      return
    }
    navigate('/dashboard')
  }

  return (
    <div style={{ padding: 16 }}>
      <Card
        title="工价管理"
        extra={
          <Space>
            {orderNo && (
              <Button onClick={() => navigate(-1)}>返回订单</Button>
            )}
            <Button onClick={goMainSystem}>返回主系统</Button>
            <Button onClick={() => navigate('/engineering/labor-price-changes')}>工价历史</Button>
            <Button type="primary" onClick={() => navigate('/engineering/labor-prices/new')}>
              新建工价
            </Button>
            <Button onClick={load} loading={loading}>
              刷新
            </Button>
          </Space>
        }
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {orderNo && (
            <Alert
              type="info"
              showIcon
              message={`来源订单：${orderNo}${lineNo ? ` / 行 ${lineNo}` : ''}`}
              description="当前页面按 BOM/产品自动筛选；这里是独立子页面。"
            />
          )}
          <Space wrap>
            <Input.Search
              allowClear
              placeholder="BOM / 产品编码 / 产品名称 / 工序"
              style={{ width: 360 }}
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onSearch={() => setPage(1)}
            />
            <Select
              allowClear
              placeholder="工序"
              style={{ width: 160 }}
              options={PROCESS_OPTIONS}
              value={processType}
              onChange={(value) => {
                setProcessType(value)
                setPage(1)
              }}
            />
          </Space>
          <Table<LaborPriceRow>
            rowKey="id"
            size="small"
            bordered
            loading={loading}
            columns={columns}
            dataSource={rows}
            scroll={{ x: 1900 }}
            pagination={{
              current: page,
              pageSize,
              total,
              showSizeChanger: true,
              pageSizeOptions: [20, 50, 100, 200],
              showTotal: (value) => `共 ${value} 条`,
              onChange: (nextPage, nextPageSize) => {
                setPage(nextPageSize !== pageSize ? 1 : nextPage)
                setPageSize(nextPageSize)
              },
            }}
          />
        </Space>
      </Card>
    </div>
  )
}
