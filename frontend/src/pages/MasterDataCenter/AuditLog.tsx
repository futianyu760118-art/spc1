import { useEffect, useState } from 'react'
import { Table, Input, Button, Space, Row, Col, message } from 'antd'
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons'
import { auditApi } from '../../services/api'

export default function AuditLog() {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })
  const [keyword, setKeyword] = useState('')

  const fetchData = async (page = 1, pageSize = 20) => {
    setLoading(true)
    try {
      const params: any = { page, page_size: pageSize }
      if (keyword) params.keyword = keyword
      const res: any = await auditApi.list(params)
      setData(res.data?.items || [])
      setPagination({ current: res.data?.page || 1, pageSize: res.data?.page_size || 20, total: res.data?.total || 0 })
    } catch {
      message.error('获取审计日志失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  const columns = [
    { title: '时间', dataIndex: 'operated_at', key: 'operated_at', width: 170 },
    { title: '操作人', dataIndex: 'operator', key: 'operator', width: 100 },
    { title: '操作', dataIndex: 'action', key: 'action', width: 80 },
    { title: '表', dataIndex: 'table_name', key: 'table_name', width: 140 },
    { title: '记录ID', dataIndex: 'record_id', key: 'record_id', width: 100 },
    { title: '字段', dataIndex: 'field_name', key: 'field_name', width: 120 },
    { title: '旧值', dataIndex: 'old_value', key: 'old_value', ellipsis: true },
    { title: '新值', dataIndex: 'new_value', key: 'new_value', ellipsis: true },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <Input
              prefix={<SearchOutlined />}
              placeholder="搜索操作人 / 表名 / 字段"
              value={keyword}
              onChange={e => setKeyword(e.target.value)}
              onPressEnter={() => fetchData()}
              allowClear
              style={{ width: 300 }}
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={() => fetchData()}>刷新</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="id"
          loading={loading}
          size="small"
          scroll={{ x: 900 }}
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
