import { useCallback, useEffect, useState } from 'react'
import {
  Button,
  Card,
  Descriptions,
  Drawer,
  Input,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useNavigate } from 'react-router-dom'
import { engineeringApi } from '../../../services/engineering'

interface ChangeDetail {
  id: number
  process_type: string
  gx?: number
  original_price?: number
  price: number
  pph?: number
  bottleneck_hours?: number
  standard_capacity?: number
  manpower?: number
  oa_detail_id?: string
  remark?: string
}

interface ChangeRow {
  id: number
  bom_code?: string
  product_code?: string
  product_name?: string
  workshop_name?: string
  status: string
  source: string
  effective_date?: string
  reason?: string
  remark?: string
  applicant?: string
  created_at?: string
  details: ChangeDetail[]
}

const STATUS_COLOR: Record<string, string> = {
  pending: 'orange',
  approved: 'green',
  rejected: 'red',
  draft: 'default',
  inactive: 'default',
}

const STATUS_LABEL: Record<string, string> = {
  pending: '待审批',
  approved: '已通过',
  rejected: '已驳回',
  draft: '草稿',
  inactive: '已停用',
}

const STATUS_OPTIONS = [
  { value: 'draft', label: '草稿' },
  { value: 'pending', label: '待审批' },
  { value: 'approved', label: '已通过' },
  { value: 'rejected', label: '已驳回' },
]

export default function LaborPriceChanges() {
  const navigate = useNavigate()
  const [keyword, setKeyword] = useState('')
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [processFilter, setProcessFilter] = useState('')
  const [rows, setRows] = useState<ChangeRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [loading, setLoading] = useState(false)
  const [detailRow, setDetailRow] = useState<ChangeRow | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [approvingId, setApprovingId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await engineeringApi.listLaborPriceChanges({
        page,
        page_size: pageSize,
        keyword: keyword.trim() || undefined,
        status: statusFilter,
        process_type: processFilter.trim() || undefined,
      })
      setRows(res.data?.items || [])
      setTotal(res.data?.total || 0)
    } catch {
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [keyword, page, pageSize, processFilter, statusFilter])

  useEffect(() => {
    setPage(1)
  }, [keyword, processFilter, statusFilter])

  useEffect(() => {
    load()
  }, [load])

  const deleteDraft = async (id: number) => {
    setDeletingId(id)
    try {
      await engineeringApi.deleteLaborPriceChange(id)
      message.success('草稿已删除')
      await load()
    } catch {
      // 全局拦截器提示
    } finally {
      setDeletingId(null)
    }
  }

  const approveChange = async (id: number) => {
    setApprovingId(id)
    try {
      const res: any = await engineeringApi.approveLaborPriceChange(id)
      const affected = res.data?.affected_schedule_plans ?? 0
      const snapshots = res.data?.refreshed_snapshots ?? 0
      message.success(`已审批通过；影响排产计划 ${affected} 条，刷新快照 ${snapshots} 条`)
      await load()
    } catch {
      // 全局拦截器提示
    } finally {
      setApprovingId(null)
    }
  }

  const rejectChange = async (id: number) => {
    setApprovingId(id)
    try {
      await engineeringApi.rejectLaborPriceChange(id)
      message.success('已驳回')
      await load()
    } catch {
      // 全局拦截器提示
    } finally {
      setApprovingId(null)
    }
  }

  const columns: ColumnsType<ChangeRow> = [
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
      width: 190,
      ellipsis: true,
      render: (value?: string) => value || '-',
    },
    {
      title: '车间',
      dataIndex: 'workshop_name',
      width: 120,
      render: (value?: string) => value || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => (
        <Tag color={STATUS_COLOR[value] || 'default'}>{STATUS_LABEL[value] || value}</Tag>
      ),
    },
    {
      title: '工序明细',
      width: 360,
      render: (_, row) => (
        <Space size={4} wrap>
          {row.details.map((detail) => (
            <Tag key={detail.id}>
              {detail.process_type}：
              {detail.original_price !== null && detail.original_price !== undefined
                ? `${detail.original_price} → `
                : ''}
              {detail.price}
              {detail.remark ? ` / ${detail.remark}` : ''}
            </Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '生效日期',
      dataIndex: 'effective_date',
      width: 120,
      render: (value?: string) => value || '审批后定',
    },
    {
      title: '申请人',
      dataIndex: 'applicant',
      width: 100,
      render: (value?: string) => value || '-',
    },
    {
      title: '提交时间',
      dataIndex: 'created_at',
      width: 160,
      render: (value?: string) => (value ? dayjs(value).format('MM-DD HH:mm') : '-'),
    },
    {
      title: '原因',
      dataIndex: 'reason',
      ellipsis: true,
      render: (value?: string) => value || '-',
    },
    {
      title: '备注',
      dataIndex: 'remark',
      ellipsis: true,
      render: (value?: string) => value || '-',
    },
    {
      title: '操作',
      width: 240,
      fixed: 'right',
      render: (_, row) => (
        <Space size={0}>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setDetailRow(row)
              setDetailOpen(true)
            }}
          >
            查看
          </Button>
          {row.status === 'pending' && (
            <Popconfirm
              title="审批通过？"
              description="通过后会写回当前工价，并标记相关排产计划需要重排。"
              onConfirm={() => approveChange(row.id)}
            >
              <Button type="link" size="small" loading={approvingId === row.id}>
                通过
              </Button>
            </Popconfirm>
          )}
          {row.status === 'pending' && (
            <Popconfirm title="驳回这条工价单？" onConfirm={() => rejectChange(row.id)}>
              <Button type="link" size="small" danger loading={approvingId === row.id}>
                驳回
              </Button>
            </Popconfirm>
          )}
          {row.status === 'draft' && (
            <Button
              type="link"
              size="small"
              onClick={() => navigate(`/engineering/labor-prices/new?id=${row.id}`)}
            >
              编辑
            </Button>
          )}
          {row.status === 'draft' && (
            <Popconfirm
              title="删除这条草稿？"
              description="删除后不可恢复；已提交的历史记录不可删除。"
              onConfirm={() => deleteDraft(row.id)}
            >
              <Button type="link" size="small" danger loading={deletingId === row.id}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  const detailColumns: ColumnsType<ChangeDetail> = [
    { title: '工序', dataIndex: 'process_type', width: 120 },
    {
      title: '原价',
      dataIndex: 'original_price',
      width: 90,
      align: 'right',
      render: (value?: number) => (value === null || value === undefined ? '-' : value),
    },
    { title: '新价', dataIndex: 'price', width: 90, align: 'right' },
    {
      title: 'PPH',
      dataIndex: 'pph',
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
      title: '人数',
      dataIndex: 'manpower',
      width: 80,
      align: 'right',
      render: (value?: number) => (value === null || value === undefined ? '-' : value),
    },
    { title: '备注', dataIndex: 'remark', ellipsis: true },
  ]

  return (
    <div style={{ padding: 16 }}>
      <Card
        title="工价历史"
        extra={
          <Space>
            <Button onClick={() => navigate('/engineering/labor-prices')}>返回当前工价</Button>
            <Button type="primary" onClick={() => navigate('/engineering/labor-prices/new')}>
              新建工价
            </Button>
          </Space>
        }
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space wrap>
            <Input.Search
              allowClear
              placeholder="BOM / 产品编码 / 产品名称 / 申请人"
              style={{ width: 360 }}
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onSearch={load}
            />
            <Select
              allowClear
              placeholder="全部状态"
              style={{ width: 130 }}
              value={statusFilter}
              onChange={setStatusFilter}
              options={STATUS_OPTIONS}
            />
            <Input.Search
              allowClear
              placeholder="工序"
              style={{ width: 160 }}
              value={processFilter}
              onChange={(event) => setProcessFilter(event.target.value)}
              onSearch={load}
            />
            <Button onClick={load}>查询</Button>
          </Space>
          <Table<ChangeRow>
            rowKey="id"
            size="small"
            bordered
            loading={loading}
            columns={columns}
            dataSource={rows}
            scroll={{ x: 1800 }}
            pagination={{
              current: page,
              pageSize,
              total,
              showSizeChanger: true,
              showTotal: (value) => `共 ${value} 条`,
              onChange: (nextPage, nextPageSize) => {
                setPage(nextPage)
                setPageSize(nextPageSize)
              },
            }}
          />
          <div style={{ color: '#8c8c8c', fontSize: 12 }}>
            共 {total} 条历史记录；历史永久保留，只有草稿可编辑/删除。
          </div>
        </Space>
      </Card>

      <Drawer
        title="工价历史详情"
        width={920}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
      >
        {detailRow && (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="BOM">{detailRow.bom_code || '-'}</Descriptions.Item>
              <Descriptions.Item label="产品编码">{detailRow.product_code || '-'}</Descriptions.Item>
              <Descriptions.Item label="产品名称">{detailRow.product_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="车间">{detailRow.workshop_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={STATUS_COLOR[detailRow.status] || 'default'}>
                  {STATUS_LABEL[detailRow.status] || detailRow.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="申请人">{detailRow.applicant || '-'}</Descriptions.Item>
              <Descriptions.Item label="生效日期">{detailRow.effective_date || '审批后定'}</Descriptions.Item>
              <Descriptions.Item label="提交时间">
                {detailRow.created_at ? dayjs(detailRow.created_at).format('YYYY-MM-DD HH:mm') : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="原因" span={2}>{detailRow.reason || '-'}</Descriptions.Item>
              <Descriptions.Item label="备注" span={2}>{detailRow.remark || '-'}</Descriptions.Item>
            </Descriptions>
            <Table<ChangeDetail>
              rowKey="id"
              size="small"
              bordered
              columns={detailColumns}
              dataSource={detailRow.details}
              pagination={false}
              scroll={{ x: 900 }}
            />
          </Space>
        )}
      </Drawer>
    </div>
  )
}
