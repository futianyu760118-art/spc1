import { useEffect, useState } from 'react'
import { Button, Form, Input, Modal, Select, Space, message } from 'antd'
import { DownloadOutlined, PlusOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { issueApi, importExportApi } from '../../../services/api'
import IssueTable from './components/IssueTable'
import IssueDetailDrawer from './components/IssueDetailDrawer'

export default function IssueLedger() {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [currentIssue, setCurrentIssue] = useState<any>(null)
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [form] = Form.useForm()
  const [stats, setStats] = useState<{ open: number; in_progress: number; closed: number } | null>(null)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [createForm] = Form.useForm()

  const fetchStats = async () => {
    try {
      const [openRes, inProgressRes, closedRes]: any[] = await Promise.all([
        issueApi.list({ page: 1, page_size: 1, status: 'open' }),
        issueApi.list({ page: 1, page_size: 1, status: 'in_progress' }),
        issueApi.list({ page: 1, page_size: 1, status: 'closed' }),
      ])
      setStats({
        open: openRes.data.total,
        in_progress: inProgressRes.data.total,
        closed: closedRes.data.total,
      })
    } catch {
      // 数据统计加载失败不阻断主界面
    }
  }

  const fetchData = async (page = 1, pageSize = 20) => {
    setLoading(true)
    try {
      const params: any = { page, page_size: pageSize, ...filters }
      Object.keys(params).forEach(k => { if (!params[k]) delete params[k] })
      const res: any = await issueApi.list(params)
      setData(res.data.items)
      setPagination({ current: res.data.page, pageSize: res.data.page_size, total: res.data.total })
    } catch {
      message.error('获取异常台账失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    fetchStats()
  }, [filters])

  const openEditModal = (record: any) => {
    setCurrentIssue(record)
    form.setFieldsValue({
      owner: record.owner,
      action_taken: record.action_taken,
      status: record.status,
      commit_date: record.commit_date ? dayjs(record.commit_date) : null,
    })
    setEditModalOpen(true)
  }

  const handleUpdate = async () => {
    try {
      const values = await form.validateFields()
      const payload: any = { ...values }
      if (values.commit_date) {
        payload.commit_date = values.commit_date.format('YYYY-MM-DD')
      }
      await issueApi.update(currentIssue.id, payload)
      message.success('更新成功')
      setEditModalOpen(false)
      fetchData(pagination.current, pagination.pageSize)
      fetchStats()
    } catch {
      message.error('更新失败')
    }
  }

  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields()
      await issueApi.create(values)
      message.success('异常问题创建成功')
      setCreateModalOpen(false)
      createForm.resetFields()
      fetchData(1, pagination.pageSize)
      fetchStats()
    } catch {
      message.error('创建失败')
    }
  }

  const handleExport = async () => {
    try {
      const res: any = await importExportApi.exportIssues()
      const url = window.URL.createObjectURL(new Blob([res]))
      const link = document.createElement('a')
      link.href = url
      link.download = 'issues.xlsx'
      link.click()
    } catch {
      message.error('导出失败')
    }
  }

  return (
    <div>

      {/* 处置进度摘要 */}
      {stats && (
        <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
          {[
            { label: '待处理', value: stats.open, color: '#e11d48' },
            { label: '处理中', value: stats.in_progress, color: '#d97706' },
            { label: '已关闭', value: stats.closed, color: '#10b981' },
            { label: '合计', value: stats.open + stats.in_progress + stats.closed, color: '#334155' },
          ].map(({ label, value, color }) => (
            <div key={label} className="card-modern" style={{ flex: 1, padding: '12px 20px' }}>
              <div style={{ color: '#94a3b8', fontSize: 12, marginBottom: 4 }}>{label}</div>
              <div style={{ fontSize: 24, fontWeight: 700, color }}>{value}</div>
            </div>
          ))}
        </div>
      )}

      {/* 筛选区 */}
      <div className="filter-bar" style={{ marginBottom: 14 }}>
        <div className="filter-left">
          <Input.Search
            placeholder="搜索问题编号 / 订单号 / 物料"
            allowClear
            onSearch={(v) => setFilters(f => ({ ...f, keyword: v }))}
            style={{ width: 280 }}
          />
          <Select
            placeholder="状态"
            allowClear
            style={{ width: 120 }}
            onChange={(v) => setFilters(f => ({ ...f, status: v || '' }))}
            options={[
              { value: 'open', label: '待处理' },
              { value: 'in_progress', label: '处理中' },
              { value: 'closed', label: '已关闭' },
            ]}
          />
          <Select
            placeholder="类型"
            allowClear
            style={{ width: 140 }}
            onChange={(v) => setFilters(f => ({ ...f, issue_type: v || '' }))}
            options={[
              { value: 'delivery_delay', label: '交期延期' },
              { value: 'shortage', label: '欠料风险' },
              { value: 'eta_delay', label: 'ETA延期' },
              { value: 'process_lag', label: '工序滞后' },
              { value: 'quality', label: '品质异常' },
              { value: 'inspection_ng', label: '客检NG' },
              { value: 'holiday_risk', label: '假期风险' },
              { value: 'long_lead', label: '长周期物料' },
            ]}
          />
          <Select
            placeholder="风险等级"
            allowClear
            style={{ width: 120 }}
            onChange={(v) => setFilters(f => ({ ...f, risk_level: v || '' }))}
            options={[
              { value: 'red', label: '高风险' },
              { value: 'yellow', label: '中风险' },
            ]}
          />
        </div>
        <div className="filter-right">
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { createForm.resetFields(); setCreateModalOpen(true) }}>
            新建异常
          </Button>
          <Button icon={<DownloadOutlined />} onClick={handleExport}>
            导出台账
          </Button>
        </div>
      </div>

      <IssueTable
        data={data}
        loading={loading}
        pagination={pagination}
        onPageChange={(page, pageSize) => fetchData(page, pageSize)}
        onEdit={openEditModal}
      />

      <IssueDetailDrawer
        open={editModalOpen}
        issue={currentIssue}
        onOk={handleUpdate}
        onCancel={() => setEditModalOpen(false)}
        form={form}
      />

      {/* 新建异常问题表单 */}
      <Modal
        title="新建异常问题"
        open={createModalOpen}
        onOk={handleCreate}
        onCancel={() => setCreateModalOpen(false)}
        okText="创建"
        cancelText="取消"
        width={560}
      >
        <Form form={createForm} layout="vertical">
          <Form.Item name="issue_type" label="异常类型" rules={[{ required: true, message: '请选择类型' }]}>
            <Select options={[
              { value: 'delivery_delay', label: '交期延期' },
              { value: 'shortage', label: '欠料风险' },
              { value: 'eta_delay', label: 'ETA延期' },
              { value: 'process_lag', label: '工序滞后' },
              { value: 'quality', label: '品质异常' },
              { value: 'inspection_ng', label: '客检NG' },
              { value: 'holiday_risk', label: '假期风险' },
              { value: 'long_lead', label: '长周期物料' },
            ]} placeholder="选择异常类型" />
          </Form.Item>
          <Form.Item name="risk_level" label="风险等级" rules={[{ required: true, message: '请选择等级' }]}>
            <Select options={[
              { value: 'red', label: '高风险（红）' },
              { value: 'yellow', label: '中风险（黄）' },
            ]} placeholder="选择风险等级" />
          </Form.Item>
          <Form.Item name="order_no" label="订单号">
            <Input placeholder="如 ORD-2026-001" />
          </Form.Item>
          <Form.Item name="line_no" label="行号">
            <Input placeholder="如 1" />
          </Form.Item>
          <Form.Item name="material_code" label="物料编码">
            <Input placeholder="如 M001" />
          </Form.Item>
          <Form.Item name="po_no" label="PO号">
            <Input placeholder="如 PO-2026-001" />
          </Form.Item>
          <Form.Item name="description" label="问题描述" rules={[{ required: true, message: '请填写描述' }]}>
            <Input.TextArea rows={3} placeholder="描述异常情况及影响" />
          </Form.Item>
          <Form.Item name="owner" label="责任人">
            <Input placeholder="填写负责人姓名或工号" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
