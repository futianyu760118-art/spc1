import { useState, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, Select, Space, message,
  Popconfirm, Tag, Switch, InputNumber,
} from 'antd'
import { PlusOutlined, EditOutlined, PlayCircleOutlined } from '@ant-design/icons'
import api from '../../services/api'

const { TextArea } = Input

interface WritebackConfigItem {
  id: number
  writeback_type: string
  description: string
  target_table: string
  target_key_fields: string | null
  update_sql_template: string | null
  field_mapping_json: string | null
  enqueue_trigger: string
  max_retries: number
  enabled: boolean
  updated_at: string | null
}

export default function WritebackConfig() {
  const [data, setData] = useState<WritebackConfigItem[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<WritebackConfigItem | null>(null)
  const [testModalOpen, setTestModalOpen] = useState(false)
  const [testResult, setTestResult] = useState<any>(null)
  const [testingType, setTestingType] = useState<string | null>(null)
  const [form] = Form.useForm()

  const fetchData = async () => {
    setLoading(true)
    try {
      const res: any = await api.get('/writeback/config')
      setData(res.data || [])
    } catch {
      message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  const openAdd = () => {
    setEditingItem(null)
    form.resetFields()
    form.setFieldsValue({ enqueue_trigger: 'auto', max_retries: 3, enabled: true })
    setModalOpen(true)
  }

  const openEdit = (record: WritebackConfigItem) => {
    setEditingItem(record)
    form.setFieldsValue({
      ...record,
      target_key_fields: record.target_key_fields || '',
      update_sql_template: record.update_sql_template || '',
      field_mapping_json: record.field_mapping_json || '',
    })
    setModalOpen(true)
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      const payload = {
        ...values,
        target_key_fields: typeof values.target_key_fields === 'string'
          ? JSON.parse(values.target_key_fields || '[]')
          : values.target_key_fields,
        field_mapping_json: values.field_mapping_json
          ? (typeof values.field_mapping_json === 'string'
              ? JSON.parse(values.field_mapping_json || '{}')
              : values.field_mapping_json)
          : null,
      }
      await api.post('/writeback/config', payload)
      message.success(editingItem ? '更新成功' : '创建成功')
      setModalOpen(false)
      fetchData()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '保存失败')
    }
  }

  const handleToggleEnabled = async (record: WritebackConfigItem) => {
    try {
      await api.post('/writeback/config', {
        writeback_type: record.writeback_type,
        description: record.description,
        target_table: record.target_table,
        target_key_fields: typeof record.target_key_fields === 'string'
          ? JSON.parse(record.target_key_fields || '[]')
          : (record.target_key_fields || []),
        update_sql_template: record.update_sql_template || '',
        field_mapping_json: typeof record.field_mapping_json === 'string'
          ? JSON.parse(record.field_mapping_json || '{}')
          : (record.field_mapping_json || null),
        enqueue_trigger: record.enqueue_trigger,
        max_retries: record.max_retries,
        enabled: !record.enabled,
      })
      message.success(record.enabled ? '已禁用' : '已启用')
      fetchData()
    } catch {
      message.error('操作失败')
    }
  }

  const handleTest = async (writebackType: string) => {
    setTestingType(writebackType)
    setTestResult(null)
    try {
      const res: any = await api.post(`/writeback/config/${writebackType}/test`)
      setTestResult(res.data || res)
      setTestModalOpen(true)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '测试失败')
    } finally {
      setTestingType(null)
    }
  }

  const columns = [
    {
      title: '类型',
      dataIndex: 'writeback_type',
      key: 'writeback_type',
      width: 140,
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: '说明',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      width: 180,
    },
    {
      title: '目标表',
      dataIndex: 'target_table',
      key: 'target_table',
      width: 140,
      render: (v: string) => <code style={{ fontSize: 12 }}>{v}</code>,
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (v: boolean, record: WritebackConfigItem) => (
        <Switch size="small" checked={v} onChange={() => handleToggleEnabled(record)} />
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 160,
      render: (v: string | null) => v ? new Date(v).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      render: (_: any, record: WritebackConfigItem) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
          <Button
            size="small"
            icon={<PlayCircleOutlined />}
            loading={testingType === record.writeback_type}
            onClick={() => handleTest(record.writeback_type)}
          >
            测试
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Space>
            <Button onClick={fetchData}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>添加配置</Button>
          </Space>
        </div>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="writeback_type"
          loading={loading}
          size="small"
          pagination={{ pageSize: 20, showTotal: (t: number) => `共 ${t} 条` }}
        />
      </div>

      <Modal
        title={editingItem ? '编辑回写配置' : '新增回写配置'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        width={640}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="writeback_type" label="类型" rules={[{ required: true }]}>
            <Input placeholder="如: order_status_update" disabled={!!editingItem} />
          </Form.Item>
          <Form.Item name="description" label="说明">
            <TextArea rows={2} placeholder="配置说明" />
          </Form.Item>
          <Form.Item name="target_table" label="目标表" rules={[{ required: true }]}>
            <Input placeholder="如: orders" />
          </Form.Item>
          <Form.Item name="target_key_fields" label="主键字段 (JSON)">
            <TextArea rows={2} placeholder='["order_no"]' style={{ fontFamily: 'monospace' }} />
          </Form.Item>
          <Form.Item name="update_sql_template" label="UPDATE SQL 模板">
            <TextArea rows={4} placeholder="UPDATE orders SET status = :status WHERE order_no = :order_no" style={{ fontFamily: 'monospace' }} />
          </Form.Item>
          <Form.Item name="field_mapping_json" label="字段映射 (JSON)">
            <TextArea rows={3} placeholder='{"erp_status": "status"}' style={{ fontFamily: 'monospace' }} />
          </Form.Item>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item name="enqueue_trigger" label="触发方式" style={{ flex: 1 }}>
              <Select
                options={[
                  { value: 'auto', label: '自动' },
                  { value: 'manual', label: '手动' },
                  { value: 'both', label: '两者' },
                ]}
              />
            </Form.Item>
            <Form.Item name="max_retries" label="最大重试次数" style={{ flex: 1 }}>
              <InputNumber min={0} max={10} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="enabled" label="启用" valuePropName="checked" style={{ flex: 0 }}>
              <Switch />
            </Form.Item>
          </div>
        </Form>
      </Modal>

      <Modal
        title="测试结果"
        open={testModalOpen}
        onCancel={() => setTestModalOpen(false)}
        footer={<Button onClick={() => setTestModalOpen(false)}>关闭</Button>}
        width={700}
      >
        {testResult && (
          <div>
            <pre style={{
              background: '#f5f5f5', padding: 16, borderRadius: 8,
              fontSize: 12, fontFamily: 'monospace', maxHeight: 400, overflow: 'auto',
            }}>
              {JSON.stringify(testResult, null, 2)}
            </pre>
          </div>
        )}
      </Modal>
    </div>
  )
}
