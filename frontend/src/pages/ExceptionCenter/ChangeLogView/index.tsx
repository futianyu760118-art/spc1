import { useEffect, useState, useCallback } from 'react'
import {
  Table, Input, Button, Space, message, Upload, Row, Col, Modal, Form, DatePicker,
} from 'antd'
import {
  SearchOutlined, ReloadOutlined, UploadOutlined, PlusOutlined, EditOutlined, DeleteOutlined,
} from '@ant-design/icons'
import { exceptionApi } from '../../../services/api'
import dayjs from 'dayjs'

export default function ChangeLogView() {
  const [data, setData] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [modalVisible, setModalVisible] = useState(false)
  const [editingItem, setEditingItem] = useState<any>(null)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: any = { page, page_size: pageSize }
      if (keyword) params.keyword = keyword
      const res: any = await exceptionApi.listChangeLog(params)
      setData(res.data.items)
      setTotal(res.data.total)
    } catch (e: any) {
      // 错误已由全局拦截器提示
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, keyword])

  useEffect(() => { load() }, [load])

  const handleImport = async (file: File) => {
    try {
      const res: any = await exceptionApi.importChangeLog(file)
      message.success(`导入完成：新增 ${res.data.created}，跳过 ${res.data.skipped}`)
      load()
    } catch (e: any) {
      // 错误已由全局拦截器提示
    }
    return false
  }

  const handleAdd = () => {
    setEditingItem(null)
    form.resetFields()
    setModalVisible(true)
  }

  const handleEdit = (item: any) => {
    setEditingItem(item)
    form.setFieldsValue({
      ...item,
      change_date: item.change_date ? dayjs(item.change_date) : null,
    })
    setModalVisible(true)
  }

  const handleDelete = async (id: number) => {
    try {
      await exceptionApi.deleteChangeLog(id)
      message.success('删除成功')
      load()
    } catch (e: any) {
      // 错误已由全局拦截器提示
    }
  }

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields()
      const payload = {
        ...values,
        change_date: values.change_date ? values.change_date.format('YYYY-MM-DD') : null,
      }
      if (editingItem) {
        await exceptionApi.updateChangeLog(editingItem.id, payload)
        message.success('更新成功')
      } else {
        await exceptionApi.createChangeLog(payload)
        message.success('创建成功')
      }
      setModalVisible(false)
      load()
    } catch (e: any) {
      if (e.errorFields) {
        message.error('请填写必填字段')
      }
      // 请求失败已由全局拦截器提示
    }
  }

  const columns = [
    { title: '序号', dataIndex: 'seq_no', width: 70 },
    { title: '修改人', dataIndex: 'modifier', width: 90 },
    { title: '日期', dataIndex: 'change_date', width: 100 },
    {
      title: '修改内容', dataIndex: 'change_content', ellipsis: true, width: 350,
      render: (v: string | null) => <span title={v || ''}>{v || '-'}</span>,
    },
    {
      title: '影响', dataIndex: 'impact', ellipsis: true, width: 200,
      render: (v: string | null) => <span title={v || ''}>{v || '-'}</span>,
    },
    {
      title: '互动', dataIndex: 'interaction', ellipsis: true, width: 200,
      render: (v: string | null) => <span title={v || ''}>{v || '-'}</span>,
    },
    {
      title: '操作', width: 100, fixed: 'right' as const,
      render: (_: any, record: any) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record.id)} />
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <Input
              prefix={<SearchOutlined />}
              placeholder="搜索修改内容/修改人"
              value={keyword}
              onChange={e => { setKeyword(e.target.value); setPage(1) }}
              style={{ width: 260 }}
              allowClear
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增</Button>
              <Upload beforeUpload={(f) => { handleImport(f); return false }} showUploadList={false} accept=".csv">
                <Button icon={<UploadOutlined />}>导入CSV</Button>
              </Upload>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey="id"
          dataSource={data}
          columns={columns}
          loading={loading}
          scroll={{ x: 1000 }}
          size="small"
          pagination={{
            total, current: page, pageSize,
            onChange: (p, ps) => { setPage(p); setPageSize(ps) },
            showSizeChanger: true, showTotal: t => `共 ${t} 条`,
          }}
        />
      </div>

      <Modal
        title={editingItem ? '编辑变更日志' : '新增变更日志'}
        open={modalVisible}
        onOk={handleModalOk}
        onCancel={() => setModalVisible(false)}
        width={600}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="seq_no" label="序号">
            <Input type="number" placeholder="序号" />
          </Form.Item>
          <Form.Item name="modifier" label="修改人">
            <Input placeholder="修改人" />
          </Form.Item>
          <Form.Item name="change_date" label="日期">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="change_content" label="修改内容">
            <Input.TextArea rows={3} placeholder="修改内容" />
          </Form.Item>
          <Form.Item name="impact" label="影响">
            <Input.TextArea rows={2} placeholder="影响" />
          </Form.Item>
          <Form.Item name="interaction" label="互动">
            <Input.TextArea rows={2} placeholder="互动" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
