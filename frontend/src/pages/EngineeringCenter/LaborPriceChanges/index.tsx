import { useCallback, useEffect, useState } from 'react'
import { Button, Card, Input, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useNavigate } from 'react-router-dom'
import { engineeringApi } from '../../../services/engineering'

interface ChangeDetail {
  id: number
  process_type: string
  gx?: number
  price: number
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

export default function LaborPriceChanges() {
  const navigate = useNavigate()
  const [keyword, setKeyword] = useState('')
  const [rows, setRows] = useState<ChangeRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await engineeringApi.listLaborPriceChanges({
        page: 1,
        page_size: 200,
        keyword: keyword.trim() || undefined,
      })
      setRows(res.data?.items || [])
      setTotal(res.data?.total || 0)
    } catch {
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [keyword])

  useEffect(() => {
    load()
  }, [load])

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
              {detail.process_type}：{detail.price}
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
  ]

  return (
    <div style={{ padding: 16 }}>
      <Card
        title="工价变更"
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
          <Input.Search
            allowClear
            placeholder="BOM / 产品编码 / 产品名称 / 申请人"
            style={{ width: 360 }}
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            onSearch={load}
          />
          <Table<ChangeRow>
            rowKey="id"
            size="small"
            bordered
            loading={loading}
            columns={columns}
            dataSource={rows}
            scroll={{ x: 1400 }}
            pagination={{ pageSize: 20, showTotal: (value) => `共 ${value} 条 / 当前显示 ${rows.length} 条` }}
          />
          <div style={{ color: '#8c8c8c', fontSize: 12 }}>
            共 {total} 条变更单；当前版本只保存为待审批，不直接影响排产。
          </div>
        </Space>
      </Card>
    </div>
  )
}
