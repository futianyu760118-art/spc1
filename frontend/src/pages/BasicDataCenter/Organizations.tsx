import { useState, useCallback, useEffect } from 'react'
import {
  Tree, Table, Button, Modal, Form, Input, Select, InputNumber, message,
  Space, Tag, Popconfirm, Row, Col, Card
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, UserOutlined,
  TeamOutlined
} from '@ant-design/icons'
import type { DataNode } from 'antd/es/tree'
import api from '../../services/api'

interface Organization {
  id: number
  org_code: string
  org_name: string
  org_type: string
  parent_id?: number
  leader_id?: number
  leader_name?: string
  status: number
}

interface OrganizationTreeNode {
  id: number
  org_code: string
  org_name: string
  org_type: string
  parent_id?: number
  leader_id?: number
  leader_name?: string
  oa_org_id?: string
  status: number
  data_source?: string
  children: OrganizationTreeNode[]
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

const OrganizationForm = ({ form, parentId }: { form: any, parentId?: number }) => (
  <Form form={form} layout="vertical" initialValues={{ parent_id: parentId, status: 1 }}>
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

const EmployeeForm = ({ form, orgId }: { form: any, orgId?: number }) => (
  <Form form={form} layout="vertical" initialValues={{ org_id: orgId, status: 1 }}>
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

const convertToTreeData = (nodes: OrganizationTreeNode[]): DataNode[] => {
  if (!nodes || !Array.isArray(nodes)) {
    return []
  }
  
  return nodes.map(node => {
    const childNodes = node.children && node.children.length > 0 
      ? convertToTreeData(node.children) 
      : undefined
    
    return {
      title: (
        <div className="organization-tree-node">
          <div className="organization-tree-node-main">
            <span className="organization-tree-node-name">{node.org_name}</span>
            {node.status === 0 && <Tag color="red" className="organization-tree-node-tag">已禁用</Tag>}
          </div>
          <div className="organization-tree-node-meta">
            <Tag color="blue" className="organization-tree-node-tag">{node.org_type || '未知'}</Tag>
            {node.leader_name && <Tag color="green" className="organization-tree-node-tag">{node.leader_name}</Tag>}
          </div>
        </div>
      ),
      key: String(node.oa_org_id || node.id), // 使用oa_org_id作为key，parent_id引用的是oa_org_id
      icon: <TeamOutlined />,
      children: childNodes,
    }
  })
}

export default function Organizations() {
  const [treeData, setTreeData] = useState<DataNode[]>([])
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null)
  const [selectedOrg, setSelectedOrg] = useState<OrganizationTreeNode | null>(null)
  const [employees, setEmployees] = useState<Employee[]>([])
  const [employeesLoading, setEmployeesLoading] = useState(false)
  const [treeLoading, setTreeLoading] = useState(false)
  
  // 组织表单相关
  const [orgModalVisible, setOrgModalVisible] = useState(false)
  const [editingOrg, setEditingOrg] = useState<Organization | null>(null)
  const [orgForm] = Form.useForm()
  
  // 员工表单相关
  const [empModalVisible, setEmpModalVisible] = useState(false)
  const [editingEmp, setEditingEmp] = useState<Employee | null>(null)
  const [empForm] = Form.useForm()
  
  const fetchTreeData = useCallback(async () => {
    setTreeLoading(true)
    try {
      const res: any = await api.get('/basicdata/organizations/tree')
      console.log('组织树API响应:', res)
      const data = res.data || []
      console.log('实际数据:', data)
      // 保存原始数据以便后续查找
      ;(window as any).lastOrgTreeData = data
      const treeNodes = convertToTreeData(data)
      console.log('转换后的树节点:', treeNodes)
      setTreeData(treeNodes)
    } catch (error) {
      console.error('加载组织树失败:', error)
      message.error('加载组织树失败')
    } finally {
      setTreeLoading(false)
    }
  }, [])

  const fetchEmployees = useCallback(async (orgId: number | string | null) => {
    if (!orgId) {
      setEmployees([])
      return
    }
    setEmployeesLoading(true)
    try {
      const res: any = await api.get(`/basicdata/organizations/${orgId}/employees`)
      setEmployees(res.data?.items || [])
    } catch (error) {
      message.error('加载员工列表失败')
    } finally {
      setEmployeesLoading(false)
    }
  }, [])

  const getOrgEmployeeQueryId = (org: OrganizationTreeNode | null, fallback?: string | null) => {
    return org?.oa_org_id || org?.id || fallback || null
  }

  useEffect(() => {
    fetchTreeData()
  }, [fetchTreeData])

  // 辅助函数：从树数据中查找指定 key 的组织信息
  const findOrgByKey = (nodes: OrganizationTreeNode[], key: string): OrganizationTreeNode | null => {
    for (const node of nodes) {
      const nodeKey = String(node.oa_org_id || node.id)
      if (nodeKey === key) {
        return node
      }
      if (node.children && node.children.length > 0) {
        const found = findOrgByKey(node.children, key)
        if (found) {
          return found
        }
      }
    }
    return null
  }

  const handleOrgSelect = (selectedKeys: React.Key[]) => {
    if (selectedKeys.length > 0) {
      const orgId = String(selectedKeys[0])
      setSelectedOrgId(orgId)
      
      // 从树数据中查找完整的组织信息
      const orgTreeData = (window as any).lastOrgTreeData || []
      const org = findOrgByKey(orgTreeData, orgId)
      setSelectedOrg(org)
      
      fetchEmployees(getOrgEmployeeQueryId(org, orgId))
    } else {
      setSelectedOrgId(null)
      setSelectedOrg(null)
      setEmployees([])
    }
  }

  const handleAddOrg = () => {
    setEditingOrg(null)
    orgForm.resetFields()
    if (selectedOrg) {
      orgForm.setFieldsValue({ parent_id: selectedOrg.id })
    }
    setOrgModalVisible(true)
  }

  const handleEditOrg = (org: Organization) => {
    setEditingOrg(org)
    orgForm.setFieldsValue(org)
    setOrgModalVisible(true)
  }

  const handleDeleteOrg = async (id: number) => {
    try {
      await api.delete(`/basicdata/organizations/${id}`)
      message.success('删除成功')
      fetchTreeData()
      if (selectedOrg?.id === id) {
        setSelectedOrgId(null)
        setSelectedOrg(null)
        setEmployees([])
      }
    } catch (error) {
      message.error('删除失败')
    }
  }

  const handleOrgSubmit = async () => {
    try {
      const values = await orgForm.validateFields()
      if (editingOrg) {
        await api.put(`/basicdata/organizations/${editingOrg.id}`, values)
        message.success('更新成功')
      } else {
        await api.post('/basicdata/organizations', values)
        message.success('创建成功')
      }
      setOrgModalVisible(false)
      orgForm.resetFields()
      fetchTreeData()
    } catch (error) {
      message.error('操作失败')
    }
  }

  const handleAddEmp = () => {
    setEditingEmp(null)
    empForm.resetFields()
    if (selectedOrg) {
      empForm.setFieldsValue({ org_id: getOrgEmployeeQueryId(selectedOrg) })
    }
    setEmpModalVisible(true)
  }

  const handleEditEmp = (emp: Employee) => {
    setEditingEmp(emp)
    empForm.setFieldsValue(emp)
    setEmpModalVisible(true)
  }

  const handleDeleteEmp = async (id: number) => {
    try {
      await api.delete(`/basicdata/employees/${id}`)
      message.success('删除成功')
      fetchEmployees(getOrgEmployeeQueryId(selectedOrg, selectedOrgId))
    } catch (error) {
      message.error('删除失败')
    }
  }

  const handleEmpSubmit = async () => {
    try {
      const values = await empForm.validateFields()
      if (editingEmp) {
        await api.put(`/basicdata/employees/${editingEmp.id}`, values)
        message.success('更新成功')
      } else {
        await api.post('/basicdata/employees', values)
        message.success('创建成功')
      }
      setEmpModalVisible(false)
      empForm.resetFields()
      fetchEmployees(getOrgEmployeeQueryId(selectedOrg, selectedOrgId))
    } catch (error) {
      message.error('操作失败')
    }
  }

  const employeeColumns = [
    { title: '员工工号', dataIndex: 'emp_code', key: 'emp_code', width: 120 },
    { title: '员工姓名', dataIndex: 'emp_name', key: 'emp_name', width: 120 },
    { title: '岗位', dataIndex: 'position', key: 'position', width: 120 },
    { title: '手机号', dataIndex: 'phone', key: 'phone', width: 130 },
    { title: '邮箱', dataIndex: 'email', key: 'email' },
    { 
      title: '状态', 
      dataIndex: 'status', 
      key: 'status', 
      width: 80,
      render: (status: number) => (
        <Tag color={status === 1 ? 'green' : 'red'}>{status === 1 ? '在职' : '离职'}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_: any, record: Employee) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEditEmp(record)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDeleteEmp(record.id)} okText="确认" cancelText="取消">
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="h-full">
      <Row gutter={16} className="h-full">
        <Col span={6}>
          <Card 
            title="组织架构" 
            extra={
              <Space>
                <Button icon={<ReloadOutlined />} onClick={fetchTreeData} />
                <Button type="primary" icon={<PlusOutlined />} onClick={handleAddOrg}>新增组织</Button>
              </Space>
            }
            className="h-full organization-tree-card"
            styles={{ body: { height: 'calc(100% - 57px)', overflow: 'auto', padding: '12px 10px' } }}
          >
            <Tree
              className="organization-tree"
              treeData={treeData}
              onSelect={handleOrgSelect}
              selectedKeys={selectedOrgId ? [selectedOrgId] : []}
              defaultExpandAll
              blockNode
              showLine
              showIcon
            />
          </Card>
        </Col>
        <Col span={18}>
          <Card 
            title={selectedOrgId ? `员工列表（${employees.length}）` : "请选择一个组织查看员工"}
            extra={selectedOrgId ? (
              <Space>
                <Button icon={<ReloadOutlined />} onClick={() => fetchEmployees(getOrgEmployeeQueryId(selectedOrg, selectedOrgId))} />
                <Button type="primary" icon={<UserOutlined />} onClick={handleAddEmp}>新增员工</Button>
              </Space>
            ) : null}
            className="h-full"
            styles={{ body: { height: 'calc(100% - 57px)', padding: 0 } }}
          >
            {selectedOrgId ? (
              <Table
                rowKey="id"
                columns={employeeColumns}
                dataSource={employees}
                loading={employeesLoading}
                scroll={{ x: 900, y: 'calc(100vh - 280px)' }}
                size="small"
                pagination={false}
              />
            ) : (
              <div className="flex items-center justify-center h-full text-gray-400">
                <TeamOutlined className="text-4xl mr-2" />
                <span>请在左侧选择一个组织查看该组织下的员工</span>
              </div>
            )}
          </Card>
        </Col>
      </Row>

      {/* 组织模态框 */}
      <Modal
        title={editingOrg ? '编辑组织' : '新增组织'}
        open={orgModalVisible}
        onOk={handleOrgSubmit}
        onCancel={() => setOrgModalVisible(false)}
        width={600}
      >
        <OrganizationForm form={orgForm} parentId={selectedOrg?.id || undefined} />
      </Modal>

      {/* 员工模态框 */}
      <Modal
        title={editingEmp ? '编辑员工' : '新增员工'}
        open={empModalVisible}
        onOk={handleEmpSubmit}
        onCancel={() => setEmpModalVisible(false)}
        width={600}
      >
        <EmployeeForm form={empForm} orgId={selectedOrg?.id || undefined} />
      </Modal>
    </div>
  )
}
