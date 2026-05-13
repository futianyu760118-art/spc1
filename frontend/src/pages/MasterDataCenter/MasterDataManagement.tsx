import { useState, useEffect, useCallback } from 'react'
import {
  Table, Button, Modal, Form, Input, Select, InputNumber, message,
  Tabs, Space, Tag, Popconfirm, Row, Col,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons'
import api from '../../services/api'

// 主数据类型定义
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
function MasterDataTable<T extends { id: number }>({
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

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await api.get(`/masterdata${apiPath}`)
      setData(res.data || [])
    } catch (error) {
      message.error('加载数据失败')
    } finally {
      setLoading(false)
    }
  }, [apiPath])

  useEffect(() => {
    fetchData()
  }, [fetchData])

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
      await api.delete(`/masterdata${apiPath}/${id}`)
      message.success('删除成功')
      fetchData()
    } catch (error) {
      message.error('删除失败')
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (editingItem) {
        await api.put(`/masterdata${apiPath}/${editingItem.id}`, values)
        message.success('更新成功')
      } else {
        await api.post(`/masterdata${apiPath}`, values)
        message.success('创建成功')
      }
      setModalVisible(false)
      form.resetFields()
      fetchData()
    } catch (error) {
      message.error('操作失败')
    }
  }

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
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
          pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条`, pageSizeOptions: ['20', '50', '100'] }}
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
        <Select.Option value={1}>在职</Select.Option>
        <Select.Option value={0}>离职</Select.Option>
      </Select>
    </Form.Item>
  </Form>
)

export default function MasterDataManagement() {
  const [activeTab, setActiveTab] = useState('customers')

  const customerColumns = [
    { title: '客户编码', dataIndex: 'customer_code', key: 'customer_code' },
    { title: '客户名称', dataIndex: 'customer_name', key: 'customer_name' },
    { title: '客户简称', dataIndex: 'customer_short', key: 'customer_short' },
    { title: '客户等级', dataIndex: 'customer_level', key: 'customer_level' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: number) => (
        <Tag color={status === 1 ? 'green' : 'red'}>{status === 1 ? '启用' : '禁用'}</Tag>
      ),
    },
  ]

  const supplierColumns = [
    { title: '供应商编码', dataIndex: 'supplier_code', key: 'supplier_code' },
    { title: '供应商名称', dataIndex: 'supplier_name', key: 'supplier_name' },
    { title: '供应商类型', dataIndex: 'supplier_type', key: 'supplier_type' },
    { title: '联系人', dataIndex: 'contact_person', key: 'contact_person' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: number) => (
        <Tag color={status === 1 ? 'green' : 'red'}>{status === 1 ? '启用' : '禁用'}</Tag>
      ),
    },
  ]

  const materialColumns = [
    { title: '物料编码', dataIndex: 'material_code', key: 'material_code' },
    { title: '物料名称', dataIndex: 'material_name', key: 'material_name' },
    { title: '规格型号', dataIndex: 'spec_model', key: 'spec_model' },
    { title: '物料分类', dataIndex: 'material_type', key: 'material_type' },
    { title: '计量单位', dataIndex: 'unit_of_measure', key: 'unit_of_measure' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: number) => (
        <Tag color={status === 1 ? 'green' : 'red'}>{status === 1 ? '启用' : '禁用'}</Tag>
      ),
    },
  ]

  const skuColumns = [
    { title: 'SKU编码', dataIndex: 'sku_code', key: 'sku_code' },
    { title: 'SKU名称', dataIndex: 'sku_name', key: 'sku_name' },
    { title: '关联物料ID', dataIndex: 'material_id', key: 'material_id' },
    { title: '条形码', dataIndex: 'barcode', key: 'barcode' },
  ]

  const productColumns = [
    { title: '产品编码', dataIndex: 'product_code', key: 'product_code' },
    { title: '产品线', dataIndex: 'product_line', key: 'product_line' },
    { title: '技术版本', dataIndex: 'tech_version', key: 'tech_version' },
    { title: 'BOM版本', dataIndex: 'bom_version', key: 'bom_version' },
  ]

  const warehouseColumns = [
    { title: '仓库编码', dataIndex: 'wh_code', key: 'wh_code' },
    { title: '仓库名称', dataIndex: 'wh_name', key: 'wh_name' },
    { title: '仓库类型', dataIndex: 'wh_type', key: 'wh_type' },
    {
      title: '状态',
      dataIndex: 'is_enabled',
      key: 'is_enabled',
      render: (status: number) => (
        <Tag color={status === 1 ? 'green' : 'red'}>{status === 1 ? '启用' : '禁用'}</Tag>
      ),
    },
  ]

  const processColumns = [
    { title: '工序编码', dataIndex: 'process_code', key: 'process_code' },
    { title: '工序名称', dataIndex: 'process_name', key: 'process_name' },
    { title: '工序分组', dataIndex: 'process_group', key: 'process_group' },
    { title: '工作中心', dataIndex: 'work_center', key: 'work_center' },
    {
      title: '质检点',
      dataIndex: 'is_qc_point',
      key: 'is_qc_point',
      render: (qc: number) => <Tag color={qc === 1 ? 'blue' : 'default'}>{qc === 1 ? '是' : '否'}</Tag>,
    },
  ]

  const organizationColumns = [
    { title: '组织编码', dataIndex: 'org_code', key: 'org_code' },
    { title: '组织名称', dataIndex: 'org_name', key: 'org_name' },
    { title: '组织类型', dataIndex: 'org_type', key: 'org_type' },
    { title: '父级ID', dataIndex: 'parent_id', key: 'parent_id' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: number) => (
        <Tag color={status === 1 ? 'green' : 'red'}>{status === 1 ? '启用' : '禁用'}</Tag>
      ),
    },
  ]

  const employeeColumns = [
    { title: '员工工号', dataIndex: 'emp_code', key: 'emp_code' },
    { title: '员工姓名', dataIndex: 'emp_name', key: 'emp_name' },
    { title: '所属组织ID', dataIndex: 'org_id', key: 'org_id' },
    { title: '岗位', dataIndex: 'position', key: 'position' },
    { title: '手机号', dataIndex: 'phone', key: 'phone' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: number) => (
        <Tag color={status === 1 ? 'green' : 'red'}>{status === 1 ? '在职' : '离职'}</Tag>
      ),
    },
  ]

  const items = [
    {
      key: 'customers',
      label: '客户主数据',
      children: (
        <MasterDataTable
          apiPath="/customers"
          columns={customerColumns}
          FormComponent={CustomerForm}
          title="客户主数据"
        />
      ),
    },
    {
      key: 'suppliers',
      label: '供应商主数据',
      children: (
        <MasterDataTable
          apiPath="/suppliers"
          columns={supplierColumns}
          FormComponent={SupplierForm}
          title="供应商主数据"
        />
      ),
    },
    {
      key: 'materials',
      label: '物料主数据',
      children: (
        <MasterDataTable
          apiPath="/materials"
          columns={materialColumns}
          FormComponent={MaterialForm}
          title="物料主数据"
        />
      ),
    },
    {
      key: 'skus',
      label: 'SKU主数据',
      children: (
        <MasterDataTable
          apiPath="/skus"
          columns={skuColumns}
          FormComponent={SKUForm}
          title="SKU主数据"
        />
      ),
    },
    {
      key: 'products',
      label: '产品主数据',
      children: (
        <MasterDataTable
          apiPath="/products"
          columns={productColumns}
          FormComponent={ProductForm}
          title="产品主数据"
        />
      ),
    },
    {
      key: 'warehouses',
      label: '仓库主数据',
      children: (
        <MasterDataTable
          apiPath="/warehouses"
          columns={warehouseColumns}
          FormComponent={WarehouseForm}
          title="仓库主数据"
        />
      ),
    },
    {
      key: 'processes',
      label: '工序主数据',
      children: (
        <MasterDataTable
          apiPath="/processes"
          columns={processColumns}
          FormComponent={ProcessForm}
          title="工序主数据"
        />
      ),
    },
    {
      key: 'organizations',
      label: '组织主数据',
      children: (
        <MasterDataTable
          apiPath="/organizations"
          columns={organizationColumns}
          FormComponent={OrganizationForm}
          title="组织主数据"
        />
      ),
    },
    {
      key: 'employees',
      label: '人员主数据',
      children: (
        <MasterDataTable
          apiPath="/employees"
          columns={employeeColumns}
          FormComponent={EmployeeForm}
          title="人员主数据"
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
