import { useCallback, useEffect, useState } from 'react'
import { Button, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'

export type FieldWidget = 'text' | 'textarea' | 'number' | 'date' | 'select' | 'boolean'

export type FieldConfig = {
  id: number
  doc_type: string
  field_key: string
  label: string
  widget: FieldWidget
  required: boolean
  show_in_list: boolean
  options?: string[] | null
  sort_order: number
}

export type FieldConfigApiSet = {
  list: () => Promise<any>
  create: (data: Record<string, any>) => Promise<any>
  update: (id: number, data: Record<string, any>) => Promise<any>
  remove: (id: number) => Promise<any>
}

const WIDGET_OPTIONS = [
  { value: 'text', label: '单行文本' },
  { value: 'textarea', label: '多行文本' },
  { value: 'number', label: '数字' },
  { value: 'date', label: '日期' },
  { value: 'select', label: '下拉选项' },
  { value: 'boolean', label: '开关/是否' },
]

const WIDGET_LABELS = Object.fromEntries(
  WIDGET_OPTIONS.map(option => [option.value, option.label]),
) as Record<FieldWidget, string>

type Props = {
  open: boolean
  api: FieldConfigApiSet
  onClose: () => void
  onChanged: () => void
}

export default function BusinessDocumentFieldConfigModal({ open, api, onClose, onChanged }: Props) {
  const [configs, setConfigs] = useState<FieldConfig[]>([])
  const [loading, setLoading] = useState(false)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<FieldConfig | null>(null)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.list()
      setConfigs(res.data || [])
    } catch {
      return
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => {
    if (open) load()
  }, [open, load])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ required: false, show_in_list: true, sort_order: configs.length })
    setFormOpen(true)
  }

  const openEdit = (config: FieldConfig) => {
    setEditing(config)
    form.setFieldsValue({
      label: config.label,
      widget: config.widget,
      required: config.required,
      show_in_list: config.show_in_list,
      options: config.options || [],
      sort_order: config.sort_order,
    })
    setFormOpen(true)
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      const payload = {
        ...values,
        options: values.widget === 'select' ? values.options : null,
        sort_order: values.sort_order ?? 0,
      }
      if (editing) {
        await api.update(editing.id, payload)
        message.success('字段已更新')
      } else {
        await api.create(payload)
        message.success('字段已新增')
      }
      setFormOpen(false)
      await load()
      onChanged()
    } catch (e: any) {
      if (!e?.errorFields) message.error(e?.response?.data?.detail || e.message || '保存失败')
    }
  }

  const handleDelete = async (config: FieldConfig) => {
    try {
      await api.remove(config.id)
      message.success('字段已删除')
      await load()
      onChanged()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '删除失败')
    }
  }

  const columns: ColumnsType<FieldConfig> = [
    { title: '字段名称', dataIndex: 'label' },
    { title: '类型', dataIndex: 'widget', width: 110, render: (value: FieldWidget) => WIDGET_LABELS[value] || value },
    { title: '必填', dataIndex: 'required', width: 70, render: (value: boolean) => (value ? '是' : '否') },
    { title: '列表显示', dataIndex: 'show_in_list', width: 90, render: (value: boolean) => (value ? '是' : '否') },
    {
      title: '选项',
      dataIndex: 'options',
      width: 180,
      render: (value: string[] | null) => (value?.length ? value.join('、') : '-'),
    },
    { title: '排序', dataIndex: 'sort_order', width: 70 },
    {
      title: '操作',
      width: 110,
      render: (_: any, row: FieldConfig) => (
        <Space size={4}>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)} />
          <Popconfirm title="确认删除该字段？已填写的值会一并清理" onConfirm={() => handleDelete(row)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Modal title="字段配置" open={open} onCancel={onClose} footer={null} width={900}>
      <div style={{ marginBottom: 12 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增字段</Button>
      </div>
      <Table rowKey="id" size="small" loading={loading} dataSource={configs} columns={columns} pagination={false} />
      <Modal
        title={editing ? '编辑字段' : '新增字段'}
        open={formOpen}
        onOk={handleSave}
        onCancel={() => setFormOpen(false)}
        width={520}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="label" label="字段名称" rules={[{ required: true, whitespace: true, message: '请输入字段名称' }]}>
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item name="widget" label="字段类型" rules={[{ required: true, message: '请选择字段类型' }]}>
            <Select options={WIDGET_OPTIONS} disabled={!!editing} />
          </Form.Item>
          <Form.Item name="required" label="必填" valuePropName="checked"><Switch /></Form.Item>
          <Form.Item name="show_in_list" label="列表显示" valuePropName="checked"><Switch /></Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.widget !== cur.widget}>
            {({ getFieldValue }) => getFieldValue('widget') === 'select' ? (
              <Form.Item name="options" label="下拉选项" rules={[{ required: true, message: '请至少添加一个选项' }]}>
                <Select mode="tags" tokenSeparators={[',', '，']} placeholder="输入选项后回车" />
              </Form.Item>
            ) : null}
          </Form.Item>
          <Form.Item name="sort_order" label="排序"><InputNumber precision={0} min={0} style={{ width: '100%' }} /></Form.Item>
        </Form>
      </Modal>
    </Modal>
  )
}
