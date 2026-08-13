import { useState, useCallback, useEffect, useRef } from 'react'
import { Tree, Table, Button, Input, InputNumber, Select, Space, Row, Col, Statistic, message, Tag, Empty } from 'antd'
import type { DataNode } from 'antd/es/tree'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import api from '../../../services/api'

interface SubjectNode {
  subject_id: number
  subject_category: string | null
  subject_name: string | null
  subject_code: string | null
  parent_subject_id: number | null
  item_code: string
  item_name: string | null
  period_count: number
  has_children: boolean
  child_count: number
  latest_year: number | null
  latest_month: number | null
  credit_amount_month: number
  credit_amount_year: number
}

interface PeriodRow {
  id: number
  subject_id: number
  subject_code: string | null
  subject_name: string | null
  subject_category: string | null
  item_code: string
  item_name: string | null
  fiscal_year: number
  fiscal_month: number
  credit_amount_month: number
  credit_amount_year: number
  updated_at: string | null
}

const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

function nodeKey(subjectId: number) {
  return `s-${subjectId}`
}

function parseNodeKey(key: string): number {
  return Number(key.replace('s-', ''))
}

export default function SubjectBalances() {
  const [treeData, setTreeData] = useState<DataNode[]>([])
  const [treeLoading, setTreeLoading] = useState(false)
  const [selectedSubjectId, setSelectedSubjectId] = useState<number | null>(null)
  const [selectedNode, setSelectedNode] = useState<SubjectNode | null>(null)
  const [periodRows, setPeriodRows] = useState<PeriodRow[]>([])
  const [periodLoading, setPeriodLoading] = useState(false)
  const [periodPagination, setPeriodPagination] = useState({ current: 1, pageSize: 20, total: 0 })
  const [filters, setFilters] = useState<{
    fiscalYear?: number
    fiscalMonth?: number
    subjectCategory?: string
    keyword?: string
    itemCode?: string
    itemName?: string
  }>({})
  const [defaultPeriod, setDefaultPeriod] = useState<{ year: number; month: number } | null>(null)
  const initialResolvedRef = useRef(false)

  const buildParams = useCallback(() => {
    const p: any = {}
    if (filters.fiscalYear !== undefined && filters.fiscalYear !== null) p.fiscal_year = filters.fiscalYear
    if (filters.fiscalMonth !== undefined && filters.fiscalMonth !== null) p.fiscal_month = filters.fiscalMonth
    if (filters.subjectCategory) p.subject_category = filters.subjectCategory
    if (filters.keyword) p.keyword = filters.keyword
    if (filters.itemCode) p.item_code = filters.itemCode
    if (filters.itemName) p.item_name = filters.itemName
    return p
  }, [filters])

  const loadRoots = useCallback(async () => {
    setTreeLoading(true)
    try {
      const params = !initialResolvedRef.current ? {} : buildParams()
      const res: any = await api.get('/basicdata/subject-balances/tree/roots', { params })
      if (!initialResolvedRef.current) {
        const headerPeriod = res._headers?.['x-default-period']
        if (headerPeriod) {
          const [y, m] = headerPeriod.split('-').map(Number)
          if (!Number.isNaN(y) && !Number.isNaN(m)) {
            setDefaultPeriod({ year: y, month: m })
            setFilters((f) => ({ ...f, fiscalYear: y, fiscalMonth: m }))
          }
        }
        initialResolvedRef.current = true
      }
      const items: SubjectNode[] = res.data?.items || []
      setTreeData(items.map(nodeToDataNode))
    } catch (e) {
      // 错误已由全局拦截器提示
    } finally {
      setTreeLoading(false)
    }
  }, [buildParams])

  useEffect(() => {
    loadRoots()
  }, [loadRoots])

  const onLoadChildren = useCallback(async (treeNode: any): Promise<void> => {
    const subjectId = parseNodeKey(treeNode.key)
    try {
      const res: any = await api.get(`/basicdata/subject-balances/tree/children/${subjectId}`, { params: buildParams() })
      const items: SubjectNode[] = res.data?.items || []
      setTreeData((prev) => updateChildren(prev, treeNode.key, items.map(nodeToDataNode)))
    } catch (e) {
      // 错误已由全局拦截器提示
    }
  }, [buildParams])

  const onSelect = useCallback((keys: React.Key[]) => {
    if (keys.length === 0) {
      setSelectedSubjectId(null)
      setSelectedNode(null)
      setPeriodRows([])
      setPeriodPagination({ current: 1, pageSize: 20, total: 0 })
      return
    }
    const id = parseNodeKey(String(keys[0]))
    setSelectedSubjectId(id)
    setPeriodPagination({ current: 1, pageSize: 20, total: 0 })
  }, [])

  const fetchPeriods = useCallback(async (page = 1, pageSize = 20) => {
    if (selectedSubjectId == null) return
    setPeriodLoading(true)
    try {
      const params: any = { page, page_size: pageSize, subject_id: selectedSubjectId }
      if (filters.fiscalYear !== undefined && filters.fiscalYear !== null) params.fiscal_year = filters.fiscalYear
      if (filters.fiscalMonth !== undefined && filters.fiscalMonth !== null) params.fiscal_month = filters.fiscalMonth
      const res: any = await api.get('/basicdata/subject-balances', { params })
      setPeriodRows(res.data?.items || [])
      setPeriodPagination({
        current: res.data?.page || 1,
        pageSize: res.data?.page_size || 20,
        total: res.data?.total || 0,
      })
    } catch (e) {
      // 错误已由全局拦截器提示
    } finally {
      setPeriodLoading(false)
    }
  }, [selectedSubjectId, filters.fiscalYear, filters.fiscalMonth])

  useEffect(() => {
    if (selectedSubjectId != null) {
      fetchPeriods(1, periodPagination.pageSize)
    }
  }, [selectedSubjectId, fetchPeriods])

  // 树节点选中时,保留节点信息用于右侧统计——从 treeData 查找
  useEffect(() => {
    if (selectedSubjectId == null) {
      setSelectedNode(null)
      return
    }
    const found = findNode(treeData, selectedSubjectId)
    setSelectedNode(found ? (found as any).node : null)
  }, [selectedSubjectId, treeData])

  const handleReset = () => {
    setFilters(
      defaultPeriod
        ? { fiscalYear: defaultPeriod.year, fiscalMonth: defaultPeriod.month }
        : {}
    )
    setSelectedSubjectId(null)
  }

  const periodColumns = [
    { title: '期间', key: 'period', width: 100, render: (_: any, r: PeriodRow) => `${r.fiscal_year}-${String(r.fiscal_month).padStart(2, '0')}` },
    { title: '科目类别', dataIndex: 'subject_category', key: 'subject_category', width: 120, ellipsis: true },
    { title: '科目编码', dataIndex: 'subject_code', key: 'subject_code', width: 120 },
    { title: '核算项目', key: 'item', width: 200, ellipsis: true, render: (_: any, r: PeriodRow) => r.item_code ? `${r.item_code} / ${r.item_name || ''}` : '-' },
    {
      title: '本月贷方发生',
      dataIndex: 'credit_amount_month',
      key: 'credit_amount_month',
      width: 140,
      align: 'right' as const,
      render: (v: number) => (v != null ? Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 }) : '-'),
    },
    {
      title: '年度贷方累计',
      dataIndex: 'credit_amount_year',
      key: 'credit_amount_year',
      width: 140,
      align: 'right' as const,
      render: (v: number) => (v != null ? Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 }) : '-'),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 160,
      render: (v: string) => (v ? new Date(v).toLocaleString('zh-CN') : '-'),
    },
  ]

  return (
    <div style={{ height: 'calc(100vh - 130px)', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16, flexShrink: 0 }}>
        <Row gutter={[12, 12]} align="middle">
          <Col>
            <InputNumber
              placeholder="年份"
              value={filters.fiscalYear}
              onChange={(v) => setFilters((f) => ({ ...f, fiscalYear: v ?? undefined }))}
              style={{ width: 110 }}
            />
          </Col>
          <Col>
            <Select
              placeholder="月份"
              value={filters.fiscalMonth}
              onChange={(v) => setFilters((f) => ({ ...f, fiscalMonth: v }))}
              allowClear
              style={{ width: 100 }}
              options={MONTHS.map((m) => ({ value: m, label: `${m}月` }))}
            />
          </Col>
          <Col>
            <Input
              placeholder="科目类别"
              value={filters.subjectCategory}
              onChange={(e) => setFilters((f) => ({ ...f, subjectCategory: e.target.value }))}
              style={{ width: 140 }}
              allowClear
            />
          </Col>
          <Col>
            <Input
              placeholder="科目编码/名称"
              prefix={<SearchOutlined />}
              value={filters.keyword}
              onChange={(e) => setFilters((f) => ({ ...f, keyword: e.target.value }))}
              onPressEnter={loadRoots}
              style={{ width: 220 }}
              allowClear
            />
          </Col>
          <Col>
            <Input
              placeholder="核算项目代码"
              value={filters.itemCode}
              onChange={(e) => setFilters((f) => ({ ...f, itemCode: e.target.value }))}
              style={{ width: 160 }}
              allowClear
            />
          </Col>
          <Col>
            <Input
              placeholder="核算项目名称"
              value={filters.itemName}
              onChange={(e) => setFilters((f) => ({ ...f, itemName: e.target.value }))}
              style={{ width: 160 }}
              allowClear
            />
          </Col>
          <Col>
            <Space>
              <Button type="primary" icon={<SearchOutlined />} onClick={loadRoots}>查询</Button>
              <Button onClick={handleReset}>重置</Button>
              <Button icon={<ReloadOutlined />} onClick={loadRoots}>刷新</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <Row gutter={16} style={{ flex: 1, minHeight: 0 }}>
        <Col xs={24} md={9} lg={8} style={{ height: '100%' }}>
          <div className="card-modern" style={{ padding: '12px 16px', height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <div style={{ marginBottom: 8, fontWeight: 600, flexShrink: 0 }}>科目树</div>
            <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
              {treeData.length === 0 && !treeLoading ? (
                <Empty description="暂无数据" />
              ) : (
                <Tree
                  treeData={treeData}
                  loadData={onLoadChildren}
                  onSelect={onSelect}
                  selectedKeys={selectedSubjectId != null ? [nodeKey(selectedSubjectId)] : []}
                  showLine
                  defaultExpandedKeys={[]}
                />
              )}
            </div>
          </div>
        </Col>
        <Col xs={24} md={15} lg={16} style={{ height: '100%' }}>
          <div className="card-modern" style={{ padding: '12px 16px', height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            {selectedNode ? (
              <Row gutter={16} style={{ marginBottom: 12, flexShrink: 0 }}>
                <Col><Statistic title="科目" value={selectedNode.subject_name || '-'} /></Col>
                <Col><Statistic title="科目编码" value={selectedNode.subject_code || '-'} /></Col>
                <Col><Statistic title="最新期间" value={selectedNode.latest_year ? `${selectedNode.latest_year}-${String(selectedNode.latest_month).padStart(2, '0')}` : '-'} /></Col>
                <Col><Statistic title="期间数" value={selectedNode.period_count} /></Col>
                <Col><Statistic title="子科目数" value={selectedNode.child_count} /></Col>
              </Row>
            ) : (
              <div style={{ marginBottom: 12, color: '#999', flexShrink: 0 }}>请选择左侧科目节点查看明细</div>
            )}
            <Table
              rowKey="id"
              columns={periodColumns}
              dataSource={periodRows}
              loading={periodLoading}
              size="small"
              scroll={{ x: 900, y: 'calc(100vh - 380px)' }}
              locale={{ emptyText: selectedSubjectId == null ? '请选择科目' : '无数据' }}
              pagination={{
                ...periodPagination,
                showSizeChanger: true,
                showTotal: (total: number) => `共 ${total} 条`,
                onChange: (page, pageSize) => fetchPeriods(page, pageSize),
                pageSizeOptions: ['20', '50', '100'],
              }}
            />
          </div>
        </Col>
      </Row>
    </div>
  )
}

function nodeToDataNode(n: SubjectNode): DataNode {
  return {
    key: nodeKey(n.subject_id),
    title: (
      <Space size={6}>
        <span>{n.subject_code || ''}</span>
        <span>{n.subject_name || '(未命名)'}</span>
        {n.child_count > 0 && <Tag color="blue">{n.child_count}子</Tag>}
        {n.credit_amount_month !== 0 && (
          <span style={{ color: '#999', fontSize: 12 }}>
            {n.latest_year ? `${n.latest_year}-${String(n.latest_month).padStart(2, '0')}:` : ''}
            {Number(n.credit_amount_month).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
        )}
      </Space>
    ) as any,
    isLeaf: !n.has_children,
    node: n,
  } as any
}

function updateChildren(data: DataNode[], key: React.Key, children: DataNode[]): DataNode[] {
  return data.map((d) => {
    if (d.key === key) {
      return { ...d, children }
    }
    if (d.children) {
      return { ...d, children: updateChildren(d.children, key, children) }
    }
    return d
  })
}

function findNode(data: DataNode[], subjectId: number): DataNode | null {
  for (const d of data) {
    if (parseNodeKey(String(d.key)) === subjectId) return d
    if (d.children) {
      const found = findNode(d.children, subjectId)
      if (found) return found
    }
  }
  return null
}