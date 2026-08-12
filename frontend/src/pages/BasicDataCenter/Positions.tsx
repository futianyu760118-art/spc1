import { useCallback, useEffect, useState } from 'react'
import { Button, Col, Input, message, Row, Select, Space, Table, Tag } from 'antd'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import api from '../../services/api'
import PermButton from '../../components/PermButton'
import { useAuthStore } from '../../store/auth'

interface Position {
  id: number
  oa_position_id?: string
  position_name: string
  status: number
  data_source?: string
  create_time: string
}

export default function Positions() {
  const [data, setData] = useState<Position[]>([])
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState<string | undefined>()
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })
  const hasPermission = useAuthStore(s => s.hasPermission)
  const canCreate = hasPermission('basicdata.data.positions', 'create')
  const canUpdate = hasPermission('basicdata.data.positions', 'update')
  const canDelete = hasPermission('basicdata.data.positions', 'delete')

  const fetchData = useCallback(async (page = 1, pageSize = 20) => {
    setLoading(true)
    try {
      const params: Record<string, any> = { page, page_size: pageSize }
      if (keyword.trim()) params.keyword = keyword.trim()
      if (status) params.status = status
      const res: any = await api.get('/basicdata/positions', { params })
      setData(res.data?.items || [])
      setPagination({
        current: res.data?.page || 1,
        pageSize: res.data?.page_size || 20,
        total: res.data?.total || 0,
      })
    } catch {
      message.error('加载岗位数据失败')
    } finally {
      setLoading(false)
    }
  }, [keyword, status])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const columns = [
    { title: 'OA岗位ID', dataIndex: 'oa_position_id', key: 'oa_position_id', sorter: true },
    { title: '岗位名称', dataIndex: 'position_name', key: 'position_name', sorter: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (value: number) => (
        <Tag color={value === 1 ? 'green' : 'red'}>{value === 1 ? '启用' : '停用'}</Tag>
      ),
    },
    {
      title: '来源',
      dataIndex: 'data_source',
      key: 'data_source',
      width: 120,
      render: (value?: string) => <Tag color={value === 'erp' ? 'blue' : 'default'}>{value || '同步'}</Tag>,
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col flex="260px">
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="搜索岗位编码/OA岗位ID/名称"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onPressEnter={() => fetchData(1, pagination.pageSize)}
            />
          </Col>
          <Col flex="160px">
            <Select
              allowClear
              style={{ width: '100%' }}
              placeholder="状态"
              value={status}
              onChange={setStatus}
              options={[
                { label: '启用', value: '1' },
                { label: '停用', value: '0' },
              ]}
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<SearchOutlined />} onClick={() => fetchData(1, pagination.pageSize)}>查询</Button>
              <Button icon={<ReloadOutlined />} onClick={() => fetchData()}>刷新</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={data}
          loading={loading}
          scroll={{ x: 900 }}
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
