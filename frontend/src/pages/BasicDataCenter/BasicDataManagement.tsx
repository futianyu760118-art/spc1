import { useState, useEffect, useCallback } from 'react'
import {
  Table, Button, Modal, Form, Input, Select, InputNumber, message,
  Tabs, Space, Tag, Popconfirm, Row, Col,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons'
import api from '../../services/api'
import {
  EMPLOYEE_STATUS_FILTERS,
  EMPLOYEE_STATUS_OPTIONS,
  getEmployeeStatusMeta,
} from '../../constants/employeeStatus'

// 基础数据类型定义
interface Customer {
  id: number
  customer_code: string
  customer_name: string
  customer_short?: string
  customer_level?: string
  industry_type?: string
  credit_code?: string
  status: number
  create_time: string
  update_time?: string
}

interface Supplier {
  id: number
  supplier_code: string
  supplier_name: string
  supplier_short?: string
  supplier_type?: string
  contact_person?: string
  contact_phone?: string
  payment_terms?: string
  status: number
  create_time: string
  update_time?: string
}

interface Material {
  id: number
  material_code: string
  material_name: string
  spec_model?: string
  material_type: string
  unit_of_measure: string
  brand?: string
  is_purchase: number
  is_produce: number
  status: number
  erp_sync_flag: number
}

interface SKU {
  id: number
  sku_code: string
  material_id: number
  sku_name: string
  attr_json?: string
  barcode?: string
  gross_weight?: number
  net_weight?: number
  volume?: number
  create_time: string
}

interface Product {
  id: number
  product_code: string
  product_line?: string
  tech_version?: string
  bom_version?: string
  default_warehouse?: string
  warranty_days?: number
  create_time: string
  update_time?: string
}

interface Warehouse {
  id: number
  wh_code: string
  wh_name: string
  wh_type: string
  address?: string
  manager_id?: number
  is_enabled: number
  create_time: string
}

interface Location {
  id: number
  location_id: string
  location_group_id?: string
  location_code?: string
  location_name?: string
  location_full_name?: string
  depth?: number
  detail_flag?: number
  parent_id?: string
  is_deleted?: number
  system_type?: number
  data_source?: string
  created_at: string
  updated_at: string
}

interface Process {
  id: number
  process_code: string
  process_name: string
  process_group?: string
  standard_hour?: number
  work_center?: string
  is_qc_point: number
  description?: string
}

interface Organization {
  id: number
  org_code: string
  org_name: string
  org_type: string
  parent_id?: number
  leader_id?: number
  status: number
}

interface Employee {
  id: number
  emp_code: string
  emp_name: string
  org_id: number
  position?: string
  phone?: string
  email?: string
  status: number
  create_time: string
}

// 通用表格组件
function BasicDataTable<T extends { id: number }>({
  apiPath,
  columns,
  FormComponent,
  title,
}: {
  apiPath: string
  columns: any[]
  FormComponent: any
  title: string
}) {
  const [data, setData] = useState<T[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingItem, setEditingItem] = useState<T | null>(null)
  const [form] = Form.useForm()
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })
  const [sortInfo, setSortInfo] = useState<{ sort_by?: string; sort_order?: string }>({})
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [keyword, setKeyword] = useState('')

  const fetchData = useCallback(async (page = pagination.current, pageSize = pagination.pageSize) => {
    setLoading(true)
    try {
      const params: any = { page, page_size: pageSize }
      if (sortInfo.sort_by) params.sort_by = sortInfo.sort_by
      if (sortInfo.sort_order) params.sort_order = sortInfo.sort_order
      if (keyword) params.keyword = keyword
      Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v })
      const res: any = await api.get(`/basicdata${apiPath}`, { params })
      const resData = res.data
      if (resData?.items) {
        setData(resData.items)
        setPagination({ current: resData.page || page, pageSize: resData.page_size || pageSize, total: resData.total || 0 })
      } else {
        setData(resData || [])
        setPagination(prev => ({ ...prev, total: (resData || []).length }))
      }
    } catch (error) {
      // 错误已由全局拦截器提示
    } finally {
      setLoading(false)
    }
  }, [apiPath, sortInfo, filters, keyword]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetchData(1)
  }, [sortInfo, filters]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetchData(1)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleTableChange = (_pag: any, tableFilters: any, sorter: any) => {
    const sortField = sorter.field
    const sortOrder = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : undefined
    setSortInfo({ sort_by: sortField, sort_order: sortOrder })
    const newFilters: Record<string, string> = {}
    Object.entries(tableFilters).forEach(([key, values]) => {
      if (values && (values as any[]).length > 0) {
        newFilters[key] = (values as any[]).join(',')
      }
    })
    setFilters(newFilters)
  }

  const handleAdd = () => {
    setEditingItem(null)
    form.resetFields()
    setModalVisible(true)
  }

  const handleEdit = (item: T) => {
    setEditingItem(item)
    form.setFieldsValue(item)
    setModalVisible(true)
  }

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/basicdata${apiPath}/${id}`)
      message.success('删除成功')
      fetchData()
    } catch (error) {
      // 错误已由全局拦截器提示
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (editingItem) {
        await api.put(`/basicdata${apiPath}/${editingItem.id}`, values)
        message.success('更新成功')
      } else {
        await api.post(`/basicdata${apiPath}`, values)
        message.success('创建成功')
      }
      setModalVisible(false)
      form.resetFields()
      fetchData()
    } catch (error) {
      // 错误已由全局拦截器提示
    }
  }

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <Input
              placeholder="搜索编码/名称"
              value={keyword}
              onChange={e => setKeyword(e.target.value)}
              onPressEnter={() => fetchData(1)}
              allowClear
              style={{ width: 240 }}
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={() => fetchData()}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey="id"
          columns={[
            ...columns,
            {
              title: '操作',
              key: 'action',
              width: 100,
              fixed: 'right' as const,
              render: (_: any, record: T) => (
                <Space size="small">
                  <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
                  <Popconfirm
                    title="确认删除？"
                    onConfirm={() => handleDelete(record.id)}
                    okText="确认"
                    cancelText="取消"
                  >
                    <Button size="small" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
          dataSource={data}
          loading={loading}
          scroll={{ x: 800 }}
          size="small"
          onChange={handleTableChange}
          pagination={{
            ...pagination,
            showSizeChanger: true,
            showTotal: (t: number) => `共 ${t} 条`,
            onChange: (p, ps) => fetchData(p, ps),
            pageSizeOptions: ['20', '50', '100'],
          }}
        />
      </div>

      <Modal
        title={editingItem ? `编辑${title}` : `新增${title}`}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={600}
      >
        <FormComponent form={form} />
      </Modal>
    </div>
  )
}

// 表单组件
const CustomerForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="customer_code" label="客户编码" rules={[{ required: true }]}>
      <Input placeholder="请输入客户编码" />
    </Form.Item>
    <Form.Item name="customer_name" label="客户名称" rules={[{ required: true }]}>
      <Input placeholder="请输入客户名称" />
    </Form.Item>
    <Form.Item name="customer_short" label="客户简称">
      <Input placeholder="请输入客户简称" />
    </Form.Item>
    <Form.Item name="customer_level" label="客户等级">
      <Select placeholder="请选择客户等级">
        <Select.Option value="A">A类</Select.Option>
        <Select.Option value="B">B类</Select.Option>
        <Select.Option value="C">C类</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="industry_type" label="所属行业">
      <Input placeholder="请输入所属行业" />
    </Form.Item>
    <Form.Item name="credit_code" label="统一社会信用代码">
      <Input placeholder="请输入统一社会信用代码" />
    </Form.Item>
    <Form.Item name="status" label="状态" initialValue={1}>
      <Select>
        <Select.Option value={1}>启用</Select.Option>
        <Select.Option value={0}>禁用</Select.Option>
      </Select>
    </Form.Item>
  </Form>
)

const SupplierForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="supplier_code" label="供应商编码" rules={[{ required: true }]}>
      <Input placeholder="请输入供应商编码" />
    </Form.Item>
    <Form.Item name="supplier_name" label="供应商名称" rules={[{ required: true }]}>
      <Input placeholder="请输入供应商名称" />
    </Form.Item>
    <Form.Item name="supplier_short" label="供应商简称">
      <Input placeholder="请输入供应商简称" />
    </Form.Item>
    <Form.Item name="supplier_type" label="供应商类型">
      <Input placeholder="请输入供应商类型" />
    </Form.Item>
    <Form.Item name="contact_person" label="联系人">
      <Input placeholder="请输入联系人" />
    </Form.Item>
    <Form.Item name="contact_phone" label="联系电话">
      <Input placeholder="请输入联系电话" />
    </Form.Item>
    <Form.Item name="payment_terms" label="付款条款">
      <Input placeholder="请输入付款条款" />
    </Form.Item>
    <Form.Item name="status" label="状态" initialValue={1}>
      <Select>
        <Select.Option value={1}>启用</Select.Option>
        <Select.Option value={0}>禁用</Select.Option>
      </Select>
    </Form.Item>
  </Form>
)

const MaterialForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="material_code" label="物料编码" rules={[{ required: true }]}>
      <Input placeholder="请输入物料编码" />
    </Form.Item>
    <Form.Item name="material_name" label="物料名称" rules={[{ required: true }]}>
      <Input placeholder="请输入物料名称" />
    </Form.Item>
    <Form.Item name="spec_model" label="规格型号">
      <Input placeholder="请输入规格型号" />
    </Form.Item>
    <Form.Item name="material_type" label="物料分类" rules={[{ required: true }]}>
      <Input placeholder="请输入物料分类" />
    </Form.Item>
    <Form.Item name="unit_of_measure" label="计量单位" rules={[{ required: true }]}>
      <Input placeholder="请输入计量单位" />
    </Form.Item>
    <Form.Item name="brand" label="品牌/厂商">
      <Input placeholder="请输入品牌/厂商" />
    </Form.Item>
    <Form.Item name="is_purchase" label="是否可采购" initialValue={0}>
      <Select>
        <Select.Option value={1}>是</Select.Option>
        <Select.Option value={0}>否</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="is_produce" label="是否可生产" initialValue={0}>
      <Select>
        <Select.Option value={1}>是</Select.Option>
        <Select.Option value={0}>否</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="status" label="状态" initialValue={1}>
      <Select>
        <Select.Option value={1}>启用</Select.Option>
        <Select.Option value={0}>禁用</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="erp_sync_flag" label="ERP同步标识" initialValue={0}>
      <Select>
        <Select.Option value={1}>已同步</Select.Option>
        <Select.Option value={0}>未同步</Select.Option>
      </Select>
    </Form.Item>
  </Form>
)

const SKUForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="sku_code" label="SKU编码" rules={[{ required: true }]}>
      <Input placeholder="请输入SKU编码" />
    </Form.Item>
    <Form.Item name="material_id" label="关联物料ID" rules={[{ required: true }]}>
      <InputNumber style={{ width: '100%' }} placeholder="请输入关联物料ID" />
    </Form.Item>
    <Form.Item name="sku_name" label="SKU名称" rules={[{ required: true }]}>
      <Input placeholder="请输入SKU名称" />
    </Form.Item>
    <Form.Item name="attr_json" label="属性JSON">
      <Input.TextArea placeholder="请输入属性JSON" rows={3} />
    </Form.Item>
    <Form.Item name="barcode" label="条形码">
      <Input placeholder="请输入条形码" />
    </Form.Item>
    <Form.Item name="gross_weight" label="毛重(KG)">
      <InputNumber style={{ width: '100%' }} placeholder="请输入毛重" />
    </Form.Item>
    <Form.Item name="net_weight" label="净重(KG)">
      <InputNumber style={{ width: '100%' }} placeholder="请输入净重" />
    </Form.Item>
    <Form.Item name="volume" label="体积(CBM)">
      <InputNumber style={{ width: '100%' }} placeholder="请输入体积" />
    </Form.Item>
  </Form>
)

const ProductForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="product_code" label="产品编码" rules={[{ required: true }]}>
      <Input placeholder="请输入产品编码" />
    </Form.Item>
    <Form.Item name="product_line" label="产品线">
      <Input placeholder="请输入产品线" />
    </Form.Item>
    <Form.Item name="tech_version" label="技术版本">
      <Input placeholder="请输入技术版本" />
    </Form.Item>
    <Form.Item name="bom_version" label="BOM版本号">
      <Input placeholder="请输入BOM版本号" />
    </Form.Item>
    <Form.Item name="default_warehouse" label="默认仓库">
      <Input placeholder="请输入默认仓库" />
    </Form.Item>
    <Form.Item name="warranty_days" label="质保天数">
      <InputNumber style={{ width: '100%' }} placeholder="请输入质保天数" />
    </Form.Item>
  </Form>
)

const WarehouseForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="wh_code" label="仓库编码" rules={[{ required: true }]}>
      <Input placeholder="请输入仓库编码" />
    </Form.Item>
    <Form.Item name="wh_name" label="仓库名称" rules={[{ required: true }]}>
      <Input placeholder="请输入仓库名称" />
    </Form.Item>
    <Form.Item name="wh_type" label="仓库类型" rules={[{ required: true }]}>
      <Select placeholder="请选择仓库类型">
        <Select.Option value="原料仓">原料仓</Select.Option>
        <Select.Option value="成品仓">成品仓</Select.Option>
        <Select.Option value="包材仓">包材仓</Select.Option>
        <Select.Option value="线边仓">线边仓</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="address" label="仓库地址">
      <Input placeholder="请输入仓库地址" />
    </Form.Item>
    <Form.Item name="manager_id" label="仓库管理员ID">
      <InputNumber style={{ width: '100%' }} placeholder="请输入仓库管理员ID" />
    </Form.Item>
    <Form.Item name="is_enabled" label="是否启用" initialValue={1}>
      <Select>
        <Select.Option value={1}>启用</Select.Option>
        <Select.Option value={0}>禁用</Select.Option>
      </Select>
    </Form.Item>
  </Form>
)

const LocationForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="location_id" label="库位ID" rules={[{ required: true }]}>
      <Input placeholder="请输入库位ID" />
    </Form.Item>
    <Form.Item name="location_code" label="库位编码">
      <Input placeholder="请输入库位编码" />
    </Form.Item>
    <Form.Item name="location_name" label="库位名称">
      <Input placeholder="请输入库位名称" />
    </Form.Item>
    <Form.Item name="location_full_name" label="库位全称">
      <Input placeholder="请输入库位全称" />
    </Form.Item>
    <Form.Item name="location_group_id" label="库位分组ID">
      <Input placeholder="请输入库位分组ID" />
    </Form.Item>
    <Form.Item name="parent_id" label="父库位ID">
      <Input placeholder="请输入父库位ID" />
    </Form.Item>
    <Form.Item name="depth" label="层级深度" initialValue={0}>
      <InputNumber style={{ width: '100%' }} placeholder="请输入层级深度" />
    </Form.Item>
    <Form.Item name="detail_flag" label="明细标识" initialValue={0}>
      <Select>
        <Select.Option value={1}>是</Select.Option>
        <Select.Option value={0}>否</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="system_type" label="系统类型" initialValue={0}>
      <InputNumber style={{ width: '100%' }} placeholder="请输入系统类型" />
    </Form.Item>
    <Form.Item name="is_deleted" label="是否删除" initialValue={0}>
      <Select>
        <Select.Option value={1}>是</Select.Option>
        <Select.Option value={0}>否</Select.Option>
      </Select>
    </Form.Item>
  </Form>
)

const ProcessForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="process_code" label="工序编码" rules={[{ required: true }]}>
      <Input placeholder="请输入工序编码" />
    </Form.Item>
    <Form.Item name="process_name" label="工序名称" rules={[{ required: true }]}>
      <Input placeholder="请输入工序名称" />
    </Form.Item>
    <Form.Item name="process_group" label="工序分组">
      <Input placeholder="请输入工序分组" />
    </Form.Item>
    <Form.Item name="standard_hour" label="标准工时">
      <InputNumber style={{ width: '100%' }} placeholder="请输入标准工时" />
    </Form.Item>
    <Form.Item name="work_center" label="工作中心">
      <Input placeholder="请输入工作中心" />
    </Form.Item>
    <Form.Item name="is_qc_point" label="是否为质检点" initialValue={0}>
      <Select>
        <Select.Option value={1}>是</Select.Option>
        <Select.Option value={0}>否</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="description" label="描述">
      <Input.TextArea placeholder="请输入描述" rows={3} />
    </Form.Item>
  </Form>
)

const OrganizationForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="org_code" label="组织编码" rules={[{ required: true }]}>
      <Input placeholder="请输入组织编码" />
    </Form.Item>
    <Form.Item name="org_name" label="组织名称" rules={[{ required: true }]}>
      <Input placeholder="请输入组织名称" />
    </Form.Item>
    <Form.Item name="org_type" label="组织类型" rules={[{ required: true }]}>
      <Select placeholder="请选择组织类型">
        <Select.Option value="部门">部门</Select.Option>
        <Select.Option value="车间">车间</Select.Option>
        <Select.Option value="班组">班组</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="parent_id" label="父级组织ID">
      <InputNumber style={{ width: '100%' }} placeholder="请输入父级组织ID" />
    </Form.Item>
    <Form.Item name="leader_id" label="负责人ID">
      <InputNumber style={{ width: '100%' }} placeholder="请输入负责人ID" />
    </Form.Item>
    <Form.Item name="status" label="状态" initialValue={1}>
      <Select>
        <Select.Option value={1}>启用</Select.Option>
        <Select.Option value={0}>禁用</Select.Option>
      </Select>
    </Form.Item>
  </Form>
)

const EmployeeForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="emp_code" label="员工工号" rules={[{ required: true }]}>
      <Input placeholder="请输入员工工号" />
    </Form.Item>
    <Form.Item name="emp_name" label="员工姓名" rules={[{ required: true }]}>
      <Input placeholder="请输入员工姓名" />
    </Form.Item>
    <Form.Item name="org_id" label="所属组织ID" rules={[{ required: true }]}>
      <InputNumber style={{ width: '100%' }} placeholder="请输入所属组织ID" />
    </Form.Item>
    <Form.Item name="position" label="岗位名称">
      <Input placeholder="请输入岗位名称" />
    </Form.Item>
    <Form.Item name="phone" label="手机号">
      <Input placeholder="请输入手机号" />
    </Form.Item>
    <Form.Item name="email" label="邮箱">
      <Input placeholder="请输入邮箱" />
    </Form.Item>
    <Form.Item name="status" label="状态" initialValue={1}>
      <Select>
        {EMPLOYEE_STATUS_OPTIONS.map(option => (
          <Select.Option key={option.value} value={option.value}>{option.label}</Select.Option>
        ))}
      </Select>
    </Form.Item>
  </Form>
)

export default function BasicDataManagement() {
  const [activeTab, setActiveTab] = useState('customers')

  const customerColumns = [
    { title: '客户编码', dataIndex: 'customer_code', key: 'customer_code', sorter: true },
    { title: '客户名称', dataIndex: 'customer_name', key: 'customer_name', sorter: true },
    { title: '客户简称', dataIndex: 'customer_short', key: 'customer_short', sorter: true },
    { title: '客户等级', dataIndex: 'customer_level', key: 'customer_level', sorter: true, filters: [{ text: 'A类', value: 'A' }, { text: 'B类', value: 'B' }, { text: 'C类', value: 'C' }] },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      sorter: true,
      filters: [{ text: '启用', value: '1' }, { text: '禁用', value: '0' }],
      render: (status: number) => (
        <Tag color={status === 1 ? 'green' : 'red'}>{status === 1 ? '启用' : '禁用'}</Tag>
      ),
    },
  ]

  const supplierColumns = [
    { title: '供应商编码', dataIndex: 'supplier_code', key: 'supplier_code', sorter: true },
    { title: '供应商名称', dataIndex: 'supplier_name', key: 'supplier_name', sorter: true },
    { title: '供应商类型', dataIndex: 'supplier_type', key: 'supplier_type', sorter: true },
    { title: '联系人', dataIndex: 'contact_person', key: 'contact_person', sorter: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      sorter: true,
      filters: [{ text: '启用', value: '1' }, { text: '禁用', value: '0' }],
      render: (status: number) => (
        <Tag color={status === 1 ? 'green' : 'red'}>{status === 1 ? '启用' : '禁用'}</Tag>
      ),
    },
  ]

  const materialColumns = [
    { title: '物料编码', dataIndex: 'material_code', key: 'material_code', sorter: true },
    { title: '物料名称', dataIndex: 'material_name', key: 'material_name', sorter: true },
    { title: '规格型号', dataIndex: 'spec_model', key: 'spec_model', sorter: true },
    { title: '物料分类', dataIndex: 'material_type', key: 'material_type', sorter: true },
    { title: '计量单位', dataIndex: 'unit_of_measure', key: 'unit_of_measure', sorter: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      sorter: true,
      filters: [{ text: '启用', value: '1' }, { text: '禁用', value: '0' }],
      render: (status: number) => (
        <Tag color={status === 1 ? 'green' : 'red'}>{status === 1 ? '启用' : '禁用'}</Tag>
      ),
    },
  ]

  const skuColumns = [
    { title: 'SKU编码', dataIndex: 'sku_code', key: 'sku_code', sorter: true },
    { title: 'SKU名称', dataIndex: 'sku_name', key: 'sku_name', sorter: true },
    { title: '关联物料ID', dataIndex: 'material_id', key: 'material_id', sorter: true },
    { title: '条形码', dataIndex: 'barcode', key: 'barcode', sorter: true },
  ]

  const productColumns = [
    { title: '产品编码', dataIndex: 'product_code', key: 'product_code', sorter: true },
    { title: '产品线', dataIndex: 'product_line', key: 'product_line', sorter: true },
    { title: '技术版本', dataIndex: 'tech_version', key: 'tech_version', sorter: true },
    { title: 'BOM版本', dataIndex: 'bom_version', key: 'bom_version', sorter: true },
  ]

  const warehouseColumns = [
    { title: '仓库编码', dataIndex: 'wh_code', key: 'wh_code', sorter: true },
    { title: '仓库名称', dataIndex: 'wh_name', key: 'wh_name', sorter: true },
    { title: '仓库类型', dataIndex: 'wh_type', key: 'wh_type', sorter: true, filters: [{ text: '原料仓', value: '原料仓' }, { text: '成品仓', value: '成品仓' }, { text: '包材仓', value: '包材仓' }, { text: '线边仓', value: '线边仓' }] },
    {
      title: '状态',
      dataIndex: 'is_enabled',
      key: 'is_enabled',
      sorter: true,
      filters: [{ text: '启用', value: '1' }, { text: '禁用', value: '0' }],
      render: (status: number) => (
        <Tag color={status === 1 ? 'green' : 'red'}>{status === 1 ? '启用' : '禁用'}</Tag>
      ),
    },
  ]

  const locationColumns = [
    { title: '库位ID', dataIndex: 'location_id', key: 'location_id', sorter: true },
    { title: '库位编码', dataIndex: 'location_code', key: 'location_code', sorter: true },
    { title: '库位名称', dataIndex: 'location_name', key: 'location_name', sorter: true },
    { title: '库位全称', dataIndex: 'location_full_name', key: 'location_full_name', sorter: true },
    { title: '层级', dataIndex: 'depth', key: 'depth', sorter: true, filters: [{ text: '0', value: '0' }, { text: '1', value: '1' }, { text: '2', value: '2' }, { text: '3', value: '3' }] },
    {
      title: '明细',
      dataIndex: 'detail_flag',
      key: 'detail_flag',
      sorter: true,
      filters: [{ text: '是', value: '1' }, { text: '否', value: '0' }],
      render: (flag: number) => <Tag color={flag === 1 ? 'blue' : 'default'}>{flag === 1 ? '是' : '否'}</Tag>,
    },
  ]

  const processColumns = [
    { title: '工序编码', dataIndex: 'process_code', key: 'process_code', sorter: true },
    { title: '工序名称', dataIndex: 'process_name', key: 'process_name', sorter: true },
    { title: '工序分组', dataIndex: 'process_group', key: 'process_group', sorter: true },
    { title: '工作中心', dataIndex: 'work_center', key: 'work_center', sorter: true },
    {
      title: '质检点',
      dataIndex: 'is_qc_point',
      key: 'is_qc_point',
      sorter: true,
      filters: [{ text: '是', value: '1' }, { text: '否', value: '0' }],
      render: (qc: number) => <Tag color={qc === 1 ? 'blue' : 'default'}>{qc === 1 ? '是' : '否'}</Tag>,
    },
  ]

  const organizationColumns = [
    { title: '组织编码', dataIndex: 'org_code', key: 'org_code', sorter: true },
    { title: '组织名称', dataIndex: 'org_name', key: 'org_name', sorter: true },
    { title: '组织类型', dataIndex: 'org_type', key: 'org_type', sorter: true, filters: [{ text: '部门', value: '部门' }, { text: '车间', value: '车间' }, { text: '班组', value: '班组' }] },
    { title: '父级ID', dataIndex: 'parent_id', key: 'parent_id', sorter: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      sorter: true,
      filters: [{ text: '启用', value: '1' }, { text: '禁用', value: '0' }],
      render: (status: number) => (
        <Tag color={status === 1 ? 'green' : 'red'}>{status === 1 ? '启用' : '禁用'}</Tag>
      ),
    },
  ]

  const employeeColumns = [
    { title: '员工工号', dataIndex: 'emp_code', key: 'emp_code', sorter: true },
    { title: '员工姓名', dataIndex: 'emp_name', key: 'emp_name', sorter: true },
    { title: '所属组织ID', dataIndex: 'org_id', key: 'org_id', sorter: true },
    { title: '岗位', dataIndex: 'position', key: 'position', sorter: true },
    { title: '手机号', dataIndex: 'phone', key: 'phone', sorter: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      sorter: true,
      filters: EMPLOYEE_STATUS_FILTERS,
      render: (status: number) => {
        const meta = getEmployeeStatusMeta(status)
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
  ]

  const items = [
    {
      key: 'customers',
      label: '客户',
      children: (
        <BasicDataTable
          apiPath="/customers"
          columns={customerColumns}
          FormComponent={CustomerForm}
          title="客户"
        />
      ),
    },
    {
      key: 'suppliers',
      label: '供应商',
      children: (
        <BasicDataTable
          apiPath="/suppliers"
          columns={supplierColumns}
          FormComponent={SupplierForm}
          title="供应商"
        />
      ),
    },
    {
      key: 'materials',
      label: '物料',
      children: (
        <BasicDataTable
          apiPath="/materials"
          columns={materialColumns}
          FormComponent={MaterialForm}
          title="物料"
        />
      ),
    },
    {
      key: 'skus',
      label: 'SKU',
      children: (
        <BasicDataTable
          apiPath="/skus"
          columns={skuColumns}
          FormComponent={SKUForm}
          title="SKU"
        />
      ),
    },
    {
      key: 'products',
      label: '产品',
      children: (
        <BasicDataTable
          apiPath="/products"
          columns={productColumns}
          FormComponent={ProductForm}
          title="产品"
        />
      ),
    },
    {
      key: 'warehouses',
      label: '仓库',
      children: (
        <BasicDataTable
          apiPath="/warehouses"
          columns={warehouseColumns}
          FormComponent={WarehouseForm}
          title="仓库"
        />
      ),
    },
    {
      key: 'locations',
      label: '库位',
      children: (
        <BasicDataTable
          apiPath="/locations"
          columns={locationColumns}
          FormComponent={LocationForm}
          title="库位"
        />
      ),
    },
    {
      key: 'processes',
      label: '工序',
      children: (
        <BasicDataTable
          apiPath="/processes"
          columns={processColumns}
          FormComponent={ProcessForm}
          title="工序"
        />
      ),
    },
    {
      key: 'organizations',
      label: '组织',
      children: (
        <BasicDataTable
          apiPath="/organizations"
          columns={organizationColumns}
          FormComponent={OrganizationForm}
          title="组织"
        />
      ),
    },
    {
      key: 'employees',
      label: '人员',
      children: (
        <BasicDataTable
          apiPath="/employees"
          columns={employeeColumns}
          FormComponent={EmployeeForm}
          title="人员"
        />
      ),
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '20px 24px' }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={items} />
      </div>
    </div>
  )
}
