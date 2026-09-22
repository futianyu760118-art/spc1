import { useState } from 'react'
import { Button, Checkbox, Form, Input, InputNumber, Modal, Select, Space, Table, Tag, Timeline } from 'antd'
import { PlusOutlined } from '@ant-design/icons'

export type ApprovalNodeRow = {
  seq: number
  label: string
  role: string
  condition?: { field: string; op: string; value: number }
}

export default function ApprovalChainEditor({ nodes, onChange, roleOptions }: {
  nodes: ApprovalNodeRow[]
  onChange: (nodes: ApprovalNodeRow[]) => void
  roleOptions: { value: string; label: string }[]
}) {
  const [editing, setEditing] = useState<ApprovalNodeRow | null>(null)
  const [isEdit, setIsEdit] = useState(false)
  const [form] = Form.useForm()

  const roleLabel = (v: string) => roleOptions.find(o => o.value === v)?.label || v

  const openNew = () => {
    setIsEdit(false)
    setEditing({ seq: nodes.length + 1, label: '', role: '' })
    form.setFieldsValue({ label: '', role: undefined, useCond: false, condField: 'claim_amount', condValue: 1000 })
  }
  const openEdit = (row: ApprovalNodeRow) => {
    setIsEdit(true)
    setEditing(row)
    form.setFieldsValue({
      label: row.label,
      role: row.role,
      useCond: !!row.condition,
      condField: row.condition?.field || 'claim_amount',
      condValue: row.condition?.value ?? 1000,
    })
  }

  const saveNode = async () => {
    const v = await form.validateFields()
    const row: ApprovalNodeRow = { seq: 0, label: v.label, role: v.role }
    if (v.useCond) row.condition = { field: (v.condField || '').trim() || 'claim_amount', op: '>=', value: v.condValue ?? 0 }
    // seq 不取表单值（表单无 seq 项），新增追加到末尾、编辑保留原位，统一按数组顺序重排
    const next = isEdit
      ? nodes.map(n => (n.seq === editing?.seq ? { ...row, seq: n.seq } : n))
      : [...nodes, { ...row, seq: nodes.length + 1 }]
    onChange(next.sort((a, b) => a.seq - b.seq).map((n, i) => ({ ...n, seq: i + 1 })))
    setEditing(null)
  }

  const removeNode = (row: ApprovalNodeRow) => {
    onChange(nodes.filter(n => n.seq !== row.seq).map((n, i) => ({ ...n, seq: i + 1 })))
  }

  const move = (index: number, dir: -1 | 1) => {
    const next = [...nodes]
    const target = index + dir
    if (target < 0 || target >= next.length) return
    ;[next[index], next[target]] = [next[target], next[index]]
    onChange(next.map((n, i) => ({ ...n, seq: i + 1 })))
  }

  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <Button icon={<PlusOutlined />} onClick={openNew}>新增节点</Button>
      </div>
      <Table<ApprovalNodeRow> rowKey="seq" dataSource={nodes} pagination={false}
        columns={[
          { title: '顺序', dataIndex: 'seq', width: 70 },
          { title: '节点名称', dataIndex: 'label' },
          { title: '审批角色', dataIndex: 'role', render: (v: string) => roleLabel(v) },
          { title: '触发条件', dataIndex: 'condition', render: (c: ApprovalNodeRow['condition']) => c ? <Tag color="orange">{c.field} ≥ {c.value} 元</Tag> : <Tag>始终</Tag> },
          { title: '操作', width: 220, render: (_: any, row: ApprovalNodeRow, i: number) => (
            <Space>
              <Button size="small" type="link" onClick={() => move(i, -1)} disabled={i === 0}>上移</Button>
              <Button size="small" type="link" onClick={() => move(i, 1)} disabled={i === nodes.length - 1}>下移</Button>
              <Button size="small" type="link" onClick={() => openEdit(row)}>编辑</Button>
              <Button size="small" type="link" danger onClick={() => removeNode(row)}>删除</Button>
            </Space>
          ) },
        ]} />
      <div style={{ marginTop: 24 }}>
        <div style={{ fontWeight: 600, marginBottom: 12 }}>链路预览</div>
        {nodes.length === 0 ? <div style={{ color: '#94a3b8' }}>暂无节点，审批提交将被拒绝</div> : (
          <Timeline
            items={nodes.map(n => ({
              children: (
                <Space size={8} wrap>
                  <span style={{ fontWeight: 600 }}>{n.label}</span>
                  <Tag>{roleLabel(n.role)}</Tag>
                  {n.condition && <Tag color="orange">{n.condition.field} ≥ {n.condition.value} 元时需要</Tag>}
                </Space>
              ),
            }))}
          />
        )}
      </div>
      <Modal title={isEdit ? '编辑节点' : '新增节点'} open={!!editing} onOk={saveNode} onCancel={() => setEditing(null)} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="label" label="节点名称" rules={[{ required: true, message: '请输入节点名称' }]}>
            <Input placeholder="如：部门意见" />
          </Form.Item>
          <Form.Item name="role" label="审批角色（role_code）" rules={[{ required: true, message: '请选择角色' }]}>
            <Select options={roleOptions} placeholder="选择审批角色" />
          </Form.Item>
          <Form.Item name="useCond" valuePropName="checked" initialValue={false}>
            <Checkbox>按金额条件触发（金额达到阈值才需要该级审批）</Checkbox>
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(p, c) => p.useCond !== c.useCond}>
            {({ getFieldValue }) => getFieldValue('useCond') ? (
              <>
                <Form.Item name="condField" label="条件字段" rules={[{ required: true, message: '请输入条件字段' }]}>
                  <Input placeholder="claim_amount" />
                </Form.Item>
                <Form.Item name="condValue" label="金额阈值（元，条件为 字段 ≥ 阈值）" rules={[{ required: true, message: '请输入金额阈值' }]}>
                  <InputNumber min={0} precision={0} style={{ width: 200 }} />
                </Form.Item>
              </>
            ) : null}
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
