import { useCallback, useEffect, useState } from 'react'
import { Button, Col, DatePicker, Descriptions, Drawer, Form, Input, List, Modal, Popconfirm, Row, Select, Space, Table, Tag, Tooltip, Upload, message } from 'antd'
import { DeleteOutlined, EditOutlined, HistoryOutlined, InboxOutlined, InfoCircleOutlined, PlusOutlined, ReloadOutlined, SendOutlined, UploadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { fileApi } from '../../services/api'
import { formatDate, formatDateTime } from '../../utils'

type DocumentApiSet = {
  list: (params: Record<string, any>) => Promise<any>
  create: (data: Record<string, any>) => Promise<any>
  update: (id: number, data: Record<string, any>) => Promise<any>
  remove: (id: number) => Promise<any>
  versions: (id: number) => Promise<any>
  publishVersion: (id: number, data: Record<string, any>) => Promise<any>
  publish: (id: number) => Promise<any>
  archive: (id: number) => Promise<any>
}

type Props = {
  title: string
  namespace: string
  api: DocumentApiSet
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: 'default' },
  published: { label: '已发布', color: 'green' },
  archived: { label: '已归档', color: 'orange' },
}

export default function BusinessDocumentPage({ title, namespace, api }: Props) {
  const [data, setData] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<any>(null)
  const [versionModalOpen, setVersionModalOpen] = useState(false)
  const [versionRecord, setVersionRecord] = useState<any>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [versions, setVersions] = useState<any[]>([])
  const [form] = Form.useForm()
  const [versionForm] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, any> = { page, page_size: pageSize }
      if (keyword.trim()) params.keyword = keyword.trim()
      if (status.length) params.status = status.join(',')
      const res = await api.list(params)
      setData(res.data.items || [])
      setTotal(res.data.total || 0)
    } catch (e: any) {
      message.error(e.message || `获取${title}失败`)
    } finally {
      setLoading(false)
    }
  }, [api, keyword, page, pageSize, status, title])

  useEffect(() => { load() }, [load])

  const normalizeAttachments = (files: any[] = []) =>
    files.map(file => file.response?.data || file).filter(Boolean)

  const uploadProps = {
    customRequest: async ({ file, onSuccess, onError }: any) => {
      try {
        const res: any = await fileApi.upload(file, namespace)
        onSuccess?.(res, file)
      } catch (e) {
        onError?.(e)
      }
    },
  }

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ status: 'draft', version_no: 'V1.0' })
    setModalOpen(true)
  }

  const openEdit = (row: any) => {
    setEditing(row)
    form.setFieldsValue(row)
    setModalOpen(true)
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      if (editing) {
        await api.update(editing.id, values)
        message.success('更新成功')
      } else {
        const payload = {
          ...values,
          attachments: normalizeAttachments(values.attachments?.fileList),
          effective_date: values.effective_date ? values.effective_date.format('YYYY-MM-DD') : null,
        }
        await api.create(payload)
        message.success('创建成功')
      }
      setModalOpen(false)
      load()
    } catch (e: any) {
      if (!e?.errorFields) message.error(e.message || '保存失败')
    }
  }

  const openVersion = (row: any) => {
    setVersionRecord(row)
    versionForm.resetFields()
    versionForm.setFieldsValue({ version_no: row.current_version ? `${row.current_version}.1` : 'V1.0', status: 'published' })
    setVersionModalOpen(true)
  }

  const handlePublishVersion = async () => {
    try {
      const values = await versionForm.validateFields()
      await api.publishVersion(versionRecord.id, {
        ...values,
        attachments: normalizeAttachments(values.attachments?.fileList),
        effective_date: values.effective_date ? values.effective_date.format('YYYY-MM-DD') : null,
      })
      message.success('版本已发布')
      setVersionModalOpen(false)
      load()
    } catch (e: any) {
      if (!e?.errorFields) message.error(e.message || '发布失败')
    }
  }

  const openHistory = async (row: any) => {
    setVersionRecord(row)
    setHistoryOpen(true)
    try {
      const res = await api.versions(row.id)
      setVersions(res.data || [])
    } catch (e: any) {
      message.error(e.message || '获取版本历史失败')
    }
  }

  const currentDetailVersion = versions.find(v => v.version_no === versionRecord?.current_version) || versions[0] || null

  const openDetail = async (row: any) => {
    setVersionRecord(row)
    setDetailOpen(true)
    try {
      const res = await api.versions(row.id)
      setVersions(res.data || [])
    } catch (e: any) {
      message.error(e.message || '获取详情失败')
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await api.remove(id)
      message.success('已删除')
      load()
    } catch (e: any) {
      message.error(e.message || '删除失败')
    }
  }

  const handlePublish = async (id: number) => {
    try {
      await api.publish(id)
      message.success('已发布')
      load()
    } catch (e: any) {
      message.error(e.message || '发布失败')
    }
  }

  const handleArchive = async (id: number) => {
    try {
      await api.archive(id)
      message.success('已归档')
      load()
    } catch (e: any) {
      message.error(e.message || '归档失败')
    }
  }

  const columns = [
    { title: '编码', dataIndex: 'code', width: 140 },
    { title: '标题', dataIndex: 'title', ellipsis: true },
    { title: '适用产品', dataIndex: 'applicable_product', width: 120, render: (v: string) => v || '-' },
    { title: '适用订单', dataIndex: 'applicable_order', width: 120, render: (v: string) => v || '-' },
    { title: '适用工序', dataIndex: 'applicable_process', width: 120, render: (v: string) => v || '-' },
    { title: '当前版本', dataIndex: 'current_version', width: 100, render: (v: string) => v || '-' },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (v: string) => <Tag color={STATUS_MAP[v]?.color || 'default'}>{STATUS_MAP[v]?.label || v}</Tag>,
    },
    { title: '更新时间', dataIndex: 'updated_at', width: 160, render: (v: string) => formatDateTime(v) },
    {
      title: '操作', width: 280, fixed: 'right' as const,
      render: (_: any, row: any) => (
        <Space size={4}>
          <Tooltip title="详情"><Button size="small" icon={<InfoCircleOutlined />} onClick={() => openDetail(row)} /></Tooltip>
          {row.status !== 'archived' && (
            <Tooltip title="编辑"><Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)} /></Tooltip>
          )}
          {row.status === 'draft' && (
            <Tooltip title="发布">
              <Popconfirm title="确认发布？" onConfirm={() => handlePublish(row.id)}>
                <Button size="small" type="primary" icon={<SendOutlined />} />
              </Popconfirm>
            </Tooltip>
          )}
          {row.status === 'published' && (
            <>
              <Tooltip title="升级版本"><Button size="small" icon={<PlusOutlined />} onClick={() => openVersion(row)} /></Tooltip>
              <Tooltip title="归档">
                <Popconfirm title="确认归档？" onConfirm={() => handleArchive(row.id)}>
                  <Button size="small" icon={<InboxOutlined />} />
                </Popconfirm>
              </Tooltip>
            </>
          )}
          <Tooltip title="历史"><Button size="small" icon={<HistoryOutlined />} onClick={() => openHistory(row)} /></Tooltip>
          <Tooltip title="删除">
            <Popconfirm title="确认删除？" onConfirm={() => handleDelete(row.id)}>
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          </Tooltip>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <Input.Search
              allowClear
              placeholder="搜索编码/标题/适用对象"
              value={keyword}
              onChange={e => { setKeyword(e.target.value); setPage(1) }}
              style={{ width: 260 }}
            />
          </Col>
          <Col>
            <Select
              mode="multiple"
              allowClear
              placeholder="状态"
              value={status}
              onChange={v => { setStatus(v); setPage(1) }}
              style={{ minWidth: 180 }}
              options={Object.entries(STATUS_MAP).map(([value, item]) => ({ value, label: item.label }))}
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增{title}</Button>
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
          size="small"
          scroll={{ x: 1200, y: 'calc(100vh - 300px)' }}
          pagination={{
            total,
            current: page,
            pageSize,
            showSizeChanger: true,
            onChange: (p, ps) => { setPage(p); setPageSize(ps) },
            showTotal: t => `共 ${t} 条`,
          }}
        />
      </div>

      <Modal title={editing ? `编辑${title}` : `新增${title}`} open={modalOpen} onOk={handleSave} onCancel={() => setModalOpen(false)} width={720}>
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="code" label="编码" rules={[{ required: true }]}><Input disabled={!!editing} /></Form.Item>
            </Col>
            <Col span={16}>
              <Form.Item name="title" label="标题" rules={[{ required: true }]}><Input /></Form.Item>
            </Col>
            <Col span={8}><Form.Item name="applicable_product" label="适用产品"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="applicable_order" label="适用订单"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="applicable_process" label="适用工序"><Input /></Form.Item></Col>
            {!editing && (
              <>
                <Col span={8}><Form.Item name="version_no" label="初始版本" rules={[{ required: true }]}><Input /></Form.Item></Col>
                <Col span={8}><Form.Item name="effective_date" label="生效日期"><DatePicker style={{ width: '100%' }} /></Form.Item></Col>
                <Col span={24}><Form.Item name="content" label="正文内容"><Input.TextArea rows={5} /></Form.Item></Col>
                <Col span={24}>
                  <Form.Item name="attachments" label="附件">
                    <Upload {...uploadProps} multiple>
                      <Button icon={<UploadOutlined />}>上传附件</Button>
                    </Upload>
                  </Form.Item>
                </Col>
              </>
            )}
          </Row>
        </Form>
      </Modal>

      <Modal title={`发布新版本 - ${versionRecord?.title || ''}`} open={versionModalOpen} onOk={handlePublishVersion} onCancel={() => setVersionModalOpen(false)} width={720}>
        <Form form={versionForm} layout="vertical">
          <Row gutter={16}>
            <Col span={8}><Form.Item name="version_no" label="版本号" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="effective_date" label="生效日期"><DatePicker style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={24}><Form.Item name="content" label="版本内容"><Input.TextArea rows={6} /></Form.Item></Col>
            <Col span={24}>
              <Form.Item name="attachments" label="附件">
                <Upload {...uploadProps} multiple>
                  <Button icon={<UploadOutlined />}>上传附件</Button>
                </Upload>
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      <Drawer title={`版本历史 - ${versionRecord?.title || ''}`} open={historyOpen} onClose={() => setHistoryOpen(false)} width={640}>
        <List
          dataSource={versions}
          locale={{ emptyText: '暂无版本' }}
          renderItem={(item: any) => (
            <List.Item>
              <List.Item.Meta
                title={<Space><Tag color={STATUS_MAP[item.status]?.color}>{STATUS_MAP[item.status]?.label || item.status}</Tag><span>{item.version_no}</span></Space>}
                description={
                  <div>
                    <div>生效日期：{formatDate(item.effective_date)}；发布人：{item.published_by || item.created_by || '-'}；发布时间：{formatDateTime(item.published_at || item.created_at)}</div>
                    <div style={{ whiteSpace: 'pre-wrap', marginTop: 8 }}>{item.content || '-'}</div>
                    {item.attachments?.length ? (
                      <div style={{ marginTop: 8 }}>
                        {item.attachments.map((a: any) => <Tag key={a.key || a.id}>{a.name}</Tag>)}
                      </div>
                    ) : null}
                  </div>
                }
              />
            </List.Item>
          )}
        />
      </Drawer>

      <Drawer title={`详情 - ${versionRecord?.title || ''}`} open={detailOpen} onClose={() => setDetailOpen(false)} width={640}>
        {versionRecord && (
          <>
            {versionRecord.status === 'published' && (
              <div style={{ marginBottom: 16 }}>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => { setDetailOpen(false); openVersion(versionRecord) }}>升级版本</Button>
              </div>
            )}
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="编码">{versionRecord.code}</Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={STATUS_MAP[versionRecord.status]?.color}>{STATUS_MAP[versionRecord.status]?.label || versionRecord.status}</Tag></Descriptions.Item>
              <Descriptions.Item label="标题" span={2}>{versionRecord.title}</Descriptions.Item>
              <Descriptions.Item label="适用产品">{versionRecord.applicable_product || '-'}</Descriptions.Item>
              <Descriptions.Item label="适用订单">{versionRecord.applicable_order || '-'}</Descriptions.Item>
              <Descriptions.Item label="适用工序">{versionRecord.applicable_process || '-'}</Descriptions.Item>
              <Descriptions.Item label="当前版本">{versionRecord.current_version || '-'}</Descriptions.Item>
              <Descriptions.Item label="创建人">{versionRecord.created_by || '-'}</Descriptions.Item>
              <Descriptions.Item label="更新时间" span={2}>{formatDateTime(versionRecord.updated_at)}</Descriptions.Item>
            </Descriptions>
            <div style={{ marginTop: 16, fontWeight: 500 }}>正文内容（{currentDetailVersion?.version_no || '-'}）</div>
            <div style={{ whiteSpace: 'pre-wrap', marginTop: 8 }}>{currentDetailVersion?.content || '-'}</div>
            <div style={{ marginTop: 16, fontWeight: 500 }}>附件</div>
            <div style={{ marginTop: 8 }}>
              {currentDetailVersion?.attachments?.length
                ? currentDetailVersion.attachments.map((a: any) => <Tag key={a.key || a.id}>{a.name}</Tag>)
                : <span>-</span>}
            </div>
          </>
        )}
      </Drawer>
    </div>
  )
}
