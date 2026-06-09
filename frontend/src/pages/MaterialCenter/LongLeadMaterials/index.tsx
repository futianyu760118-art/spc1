import { useEffect, useState, useCallback } from 'react'
import {
  Table, Tag, Input, Select, Button, Space, message, Modal, Form,
  Row, Col, Popconfirm, Tooltip, Card,
} from 'antd'
import {
  SearchOutlined, ReloadOutlined, EditOutlined, DeleteOutlined,
  ScanOutlined, ScheduleOutlined, ThunderboltOutlined,
  WarningOutlined, ExclamationCircleOutlined,
} from '@ant-design/icons'
import { materialApi } from '../../../services/api'

interface LongLeadDerivedRow {
  id: number | null
  material_code: string
  material_name: string | null
  supplier_name: string | null
  avg_lead_time_days: number | null
  max_lead_time_days: number | null
  po_count: number
  latest_eta: string | null
  improvement_plan: string | null
  status: string
  risk_level: string
}

const RISK_TAG_MAP: Record<string, { color: string; label: string }> = {
  danger: { color: '#e11d48', label: '高风险' },
  warning: { color: '#f59e0b', label: '中风险' },
  normal: { color: '#22c55e', label: '正常' },
}

export default function LongLeadMaterials() {
  const [data, setData] = useState<LongLeadDerivedRow[]>([])
  const [total, setTotal] = useState(0)
  const [globalStats, setGlobalStats] = useState({ total: 0, active_count: 0, danger_count: 0, warning_count: 0 })
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filters, setFilters] = useState({ keyword: '', supplier_name: '', status: '', risk_level: '' })
  const [sortBy, setSortBy] = useState<string>('')
  const [sortOrder, setSortOrder] = useState<string>('')
  const [modalOpen, setModalOpen] = useState(false)
  const [editRecord, setEditRecord] = useState<LongLeadDerivedRow | null>(null)
  const [form] = Form.useForm()
  const [scanLoading, setScanLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await materialApi.listLongLead({
        page, page_size: pageSize,
        ...(filters.keyword ? { keyword: filters.keyword } : {}),
        ...(filters.supplier_name ? { supplier_name: filters.supplier_name } : {}),
        ...(filters.status ? { status: filters.status } : {}),
        ...(filters.risk_level ? { risk_level: filters.risk_level } : {}),
        ...(sortBy ? { sort_by: sortBy, sort_order: sortOrder || 'asc' } : {}),
      })
      setData(res.data.items)
      setTotal(res.data.total)
      setGlobalStats(res.data.stats || { active_count: 0, danger_count: 0, warning_count: 0 })
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, filters, sortBy, sortOrder])

  useEffect(() => { load() }, [load])

  const handleScan = async () => {
    setScanLoading(true)
    try {
      const res: any = await materialApi.scanLongLead()
      message.success(`扫描完成：新增注解 ${res.data.new_annotations} 条`)
      load()
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setScanLoading(false)
    }
  }

  const openEdit = async (row: LongLeadDerivedRow) => {
    let annotationId = row.id
    if (!annotationId) {
      try {
        const res: any = await materialApi.ensureAnnotation({
          material_code: row.material_code,
          supplier_name: row.supplier_name,
        })
        annotationId = res.data.id
      } catch (e: any) {
        message.error(e.message)
        return
      }
    }
    setEditRecord({ ...row, id: annotationId })
    form.setFieldsValue({ improvement_plan: row.improvement_plan, status: row.status })
    setModalOpen(true)
  }

  const handleSubmit = async (values: any) => {
    if (!editRecord?.id) return
    try {
      await materialApi.updateLongLead(editRecord.id, values)
      message.success('更新成功')
      setModalOpen(false)
      load()
    } catch (e: any) {
      message.error(e.message)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await materialApi.deleteLongLead(id)
      message.success('注解已删除（物料如仍满足条件会重新出现）')
      load()
    } catch (e: any) {
      message.error(e.message)
    }
  }

  const columns = [
    {
      title: '物料代码', dataIndex: 'material_code', width: 150, ellipsis: true, sorter: true,
      render: (v: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span>,
    },
    { title: '物料名称', dataIndex: 'material_name', width: 200, ellipsis: true, sorter: true },
    {
      title: '供应商', dataIndex: 'supplier_name', width: 130, ellipsis: true, sorter: true,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '平均交期(天)', dataIndex: 'avg_lead_time_days', width: 120, sorter: true,
      render: (v: number | null) => {
        if (!v) return <span style={{ color: '#cbd5e1' }}>-</span>
        const color = v >= 30 ? '#e11d48' : v >= 25 ? '#f59e0b' : undefined
        return (
          <span style={{ color, fontWeight: color ? 600 : undefined }}>
            {v} 天 {v >= 30 ? '🔴' : v >= 25 ? '🟡' : ''}
          </span>
        )
      },
    },
    {
      title: '最长交期(天)', dataIndex: 'max_lead_time_days', width: 110, sorter: true,
      render: (v: number | null) => v != null ? `${v} 天` : <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '历史PO数', dataIndex: 'po_count', width: 90, sorter: true,
      render: (v: number) => <span>{v}</span>,
    },
    {
      title: '最近ETA', dataIndex: 'latest_eta', width: 110, sorter: true,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '改善对策', dataIndex: 'improvement_plan', width: 180, ellipsis: true,
      render: (v: string | null) => (
        <Tooltip title={v || ''}>
          <span style={{ color: v ? undefined : '#cbd5e1' }}>{v || '未填写'}</span>
        </Tooltip>
      ),
    },
    {
      title: '风险等级', dataIndex: 'risk_level', width: 90, sorter: true,
      render: (v: string) => {
        const m = RISK_TAG_MAP[v] || RISK_TAG_MAP.normal
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: '状态', dataIndex: 'status', width: 90, sorter: true,
      render: (v: string) => (
        <Tag color={v === 'active' ? 'warning' : 'default'}>
          {v === 'active' ? '启用中' : '已停产'}
        </Tag>
      ),
    },
    {
      title: '操作', width: 90, fixed: 'right' as const,
      render: (_: any, row: LongLeadDerivedRow) => (
        <Space size={4}>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)} />
          {row.id && (
            <Popconfirm title="删除注解记录？物料如仍满足条件会重新出现" onConfirm={() => handleDelete(row.id!)}>
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      {/* 统计卡 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { title: '长交期物料总数', value: globalStats.total || total, icon: <ScheduleOutlined />, color: '#6366f1' },
          { title: '当前启用', value: globalStats.active_count, icon: <ThunderboltOutlined />, color: '#f59e0b' },
          { title: '≥30天高风险', value: globalStats.danger_count, icon: <WarningOutlined />, color: '#e11d48' },
          { title: '20-29天中风险', value: globalStats.warning_count, icon: <ExclamationCircleOutlined />, color: '#f59e0b' },
        ].map((card, i) => (
          <Col span={6} key={i}>
            <Card size="small" className="card-modern" style={{ padding: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ width: 44, height: 44, borderRadius: 10, background: `${card.color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 'calc(1.25rem * var(--font-size-scale))', color: card.color }}>
                  {card.icon}
                </div>
                <div>
                  <div style={{ fontSize: 'calc(1.375rem * var(--font-size-scale))', fontWeight: 700, color: '#1e293b' }}>{card.value}</div>
                  <div style={{ fontSize: 'calc(0.75rem * var(--font-size-scale))', color: '#64748b' }}>{card.title}</div>
                </div>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <Input
              prefix={<SearchOutlined />}
              placeholder="搜索物料/供应商"
              value={filters.keyword}
              onChange={e => { setFilters(f => ({ ...f, keyword: e.target.value })); setPage(1) }}
              style={{ width: 220 }}
              allowClear
            />
          </Col>
          <Col>
            <Input
              placeholder="供应商"
              value={filters.supplier_name}
              onChange={e => { setFilters(f => ({ ...f, supplier_name: e.target.value })); setPage(1) }}
              style={{ width: 130 }}
              allowClear
            />
          </Col>
          <Col>
            <Select
              placeholder="风险等级"
              value={filters.risk_level || undefined}
              onChange={v => { setFilters(f => ({ ...f, risk_level: v || '' })); setPage(1) }}
              allowClear
              style={{ width: 110 }}
            >
              <Select.Option value="danger">高风险(≥30天)</Select.Option>
              <Select.Option value="warning">中风险(20-29天)</Select.Option>
            </Select>
          </Col>
          <Col>
            <Select
              placeholder="状态"
              value={filters.status || undefined}
              onChange={v => { setFilters(f => ({ ...f, status: v || '' })); setPage(1) }}
              allowClear
              style={{ width: 110 }}
            >
              <Select.Option value="active">启用中</Select.Option>
              <Select.Option value="discontinued">已停产</Select.Option>
            </Select>
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
              <Button icon={<ScanOutlined />} loading={scanLoading} onClick={handleScan}>扫描识别</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey={r => `${r.material_code}-${r.supplier_name}`}
          dataSource={data}
          columns={columns}
          loading={loading}
          scroll={{ x: 1400 }}
          size="small"
          pagination={{
            total, current: page, pageSize,
            showSizeChanger: true, showTotal: t => `共 ${t} 条`,
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

      <Modal
        title="编辑改善对策"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
      >
        <div style={{ marginBottom: 12, color: '#64748b', fontSize: 13 }}>
          物料：{editRecord?.material_name} | 供应商：{editRecord?.supplier_name} | 平均交期：{editRecord?.avg_lead_time_days}天
        </div>
        <Form form={form} layout="vertical" onFinish={handleSubmit} initialValues={{ status: 'active' }}>
          <Form.Item name="improvement_plan" label="改善对策">
            <Input.TextArea rows={4} placeholder="填写改善对策，如：供应商备货、产品已停产等" />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select>
              <Select.Option value="active">启用中</Select.Option>
              <Select.Option value="discontinued">已停产</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
