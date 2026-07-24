import { useState, useCallback, useEffect } from 'react'
import { Table, Button, Input, message, Space, Row, Col, Statistic } from 'antd'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import api from '../../services/api'

interface InventoryItem {
  id: number
  material_id: number
  material_code: string
  material_name: string
  wh_id: number
  wh_code: string
  wh_name: string
  location_id: number | null
  location_name: string
  qty_on_hand: number
  locked_qty: number
  balance_qty: number
  qty_in_transit: number
  batch_no: string
  created_at: string
  updated_at: string
}

export default function Inventory() {
  const [data, setData] = useState<InventoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [totals, setTotals] = useState({ onHand: 0, locked: 0, balance: 0, inTransit: 0 })
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })

  const fetchData = useCallback(async (page = 1, pageSize = 20) => {
    setLoading(true)
    try {
      const params: any = { page, page_size: pageSize }
      if (keyword) params.keyword = keyword
      const res: any = await api.get('/basicdata/inventory', { params })
      const items = res.data?.items || []
      setData(items)
      setPagination({
        current: res.data?.page || 1,
        pageSize: res.data?.page_size || 20,
        total: res.data?.total || 0,
      })

      const sum = items.reduce(
        (acc: any, item: InventoryItem) => ({
          onHand: acc.onHand + (item.qty_on_hand || 0),
          locked: acc.locked + (item.locked_qty || 0),
          balance: acc.balance + (item.balance_qty || 0),
          inTransit: acc.inTransit + (item.qty_in_transit || 0),
        }),
        { onHand: 0, locked: 0, balance: 0, inTransit: 0 },
      )
      setTotals(sum)
    } catch (error) {
      message.error('加载库存数据失败')
    } finally {
      setLoading(false)
    }
  }, [keyword])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const columns = [
    { title: '物料编码', dataIndex: 'material_code', key: 'material_code', width: 120 },
    { title: '物料名称', dataIndex: 'material_name', key: 'material_name', width: 160, ellipsis: true },
    { title: '仓库编码', dataIndex: 'wh_code', key: 'wh_code', width: 100 },
    { title: '仓库名称', dataIndex: 'wh_name', key: 'wh_name', width: 120 },
    { title: '库位名称', dataIndex: 'location_name', key: 'location_name', width: 120, ellipsis: true },
    {
      title: '库存量',
      dataIndex: 'qty_on_hand',
      key: 'qty_on_hand',
      width: 100,
      align: 'right' as const,
      render: (v: number) => (v != null ? v.toLocaleString() : '-'),
    },
    {
      title: '锁定数量',
      dataIndex: 'locked_qty',
      key: 'locked_qty',
      width: 100,
      align: 'right' as const,
      render: (v: number) => (v != null ? v.toLocaleString() : '-'),
    },
    {
      title: '结存数量',
      dataIndex: 'balance_qty',
      key: 'balance_qty',
      width: 100,
      align: 'right' as const,
      render: (v: number) => (v != null ? v.toLocaleString() : '-'),
    },
    {
      title: '在途库存',
      dataIndex: 'qty_in_transit',
      key: 'qty_in_transit',
      width: 100,
      align: 'right' as const,
      render: (v: number) => (v != null ? v.toLocaleString() : '-'),
    },
    { title: '批次号', dataIndex: 'batch_no', key: 'batch_no', width: 100 },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 160,
      render: (v: string) => (v ? new Date(v).toLocaleString('zh-CN') : '-'),
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={[12, 12]} align="middle">
          <Col>
            <Input
              placeholder="搜索物料编码/名称/仓库"
              prefix={<SearchOutlined />}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onPressEnter={() => fetchData(1, pagination.pageSize)}
              style={{ width: 240 }}
              allowClear
            />
          </Col>
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={() => fetchData(pagination.current, pagination.pageSize)}>刷新</Button>
            </Space>
          </Col>
        </Row>
        <Row gutter={16} style={{ marginTop: 12 }}>
          <Col>
            <Statistic title="库存量合计" value={totals.onHand} precision={2} />
          </Col>
          <Col>
            <Statistic title="锁定数量合计" value={totals.locked} precision={2} />
          </Col>
          <Col>
            <Statistic title="结存数量合计" value={totals.balance} precision={2} />
          </Col>
          <Col>
            <Statistic title="在途库存合计" value={totals.inTransit} precision={2} />
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={data}
          loading={loading}
          scroll={{ x: 1400 }}
          size="small"
          pagination={{
            ...pagination,
            showSizeChanger: true,
            showTotal: (total: number) => `共 ${total} 条`,
            onChange: (page, pageSize) => fetchData(page, pageSize),
            pageSizeOptions: ['20', '50', '100'],
          }}
        />
      </div>
    </div>
  )
}
