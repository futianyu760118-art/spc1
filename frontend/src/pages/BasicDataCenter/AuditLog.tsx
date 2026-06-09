import { useEffect, useState, useCallback } from 'react'
import { Table, Input, Button, Space, Row, Col, message } from 'antd'
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons'
import { auditApi } from '../../services/api'

export default function AuditLog() {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })
  const [keyword, setKeyword] = useState('')
  const [sortInfo, setSortInfo] = useState<{ sort_by?: string; sort_order?: string }>({})
  const [filters, setFilters] = useState<Record<string, string[]>>({})

  const fetchData = useCallback(async (page = pagination.current, pageSize = pagination.pageSize) => {
    setLoading(true)
    try {
      const params: any = { page, page_size: pageSize }
      if (keyword) params.keyword = keyword
      if (sortInfo.sort_by) params.sort_by = sortInfo.sort_by
      if (sortInfo.sort_order) params.sort_order = sortInfo.sort_order
      if (filters.action?.length) params.action = filters.action.join(',')
      if (filters.table_name?.length) params.table_name = filters.table_name.join(',')
      if (filters.operator?.length) params.operator = filters.operator.join(',')
      const res: any = await auditApi.list(params)
      setData(res.data?.items || [])
      setPagination({ current: res.data?.page || 1, pageSize: res.data?.page_size || 20, total: res.data?.total || 0 })
    } catch {
      message.error('获取审计日志失败')
    } finally {
      setLoading(false)
    }
  }, [keyword, sortInfo, filters]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { fetchData(1) }, [sortInfo, filters]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleTableChange = (_pag: any, tableFilters: any, sorter: any) => {
    const sortField = sorter.field
    const sortOrder = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : undefined
    setSortInfo({ sort_by: sortField, sort_order: sortOrder })
    const newFilters: Record<string, string[]> = {}
    if (tableFilters.action?.length) newFilters.action = tableFilters.action
    if (tableFilters.table_name?.length) newFilters.table_name = tableFilters.table_name
    if (tableFilters.operator?.length) newFilters.operator = tableFilters.operator
    setFilters(newFilters)
  }

  // 从当前数据中提取唯一值作为筛选选项
  const uniqueValues = (key: string) => Array.from(new Set(data.map((r: any) => r[key]).filter(Boolean))).map(v => ({ text: String(v), value: v }))

  const columns = [
    { title: '时间', dataIndex: 'operated_at', key: 'operated_at', width: 170, sorter: true },
    { title: '操作人', dataIndex: 'operator', key: 'operator', width: 100, sorter: true, filters: uniqueValues('operator'), filterSearch: true },
    { title: '操作', dataIndex: 'action', key: 'action', width: 80, sorter: true, filters: uniqueValues('action') },
    { title: '表', dataIndex: 'table_name', key: 'table_name', width: 140, sorter: true, filters: uniqueValues('table_name'), filterSearch: true },
    { title: '记录ID', dataIndex: 'record_id', key: 'record_id', width: 100, sorter: true },
    { title: '字段', dataIndex: 'field_name', key: 'field_name', width: 120, sorter: true },
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
              onPressEnter={() => fetchData(1)}
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
          onChange={handleTableChange}
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
