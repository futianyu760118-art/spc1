import React, { useState } from 'react'
import { Alert, Table, Tag } from 'antd'
import { DownOutlined, UpOutlined } from '@ant-design/icons'
import type { MaterialItem } from '../index'

const MATERIAL_STATUS_COLOR: Record<string, string> = {
  not_ordered: 'volcano',
  self_made_unlinked: 'blue',
  partial_received: 'warning',
  fully_received: 'success',
  overdue: 'error',
  pending: 'cyan',
  in_stock: 'green',
}

const fmt = (v: number | null | undefined) => (v == null ? '-' : Number(v).toLocaleString())

interface Props {
  orphans: MaterialItem[]
}

const OrphanMaterialAlert: React.FC<Props> = ({ orphans }) => {
  const [expanded, setExpanded] = useState(false)
  if (!orphans || orphans.length === 0) return null

  const columns = [
    { title: '物料编码', dataIndex: 'material_code', key: 'material_code', width: 140 },
    { title: '物料名称', dataIndex: 'material_name', key: 'material_name', width: 180 },
    { title: '属性', dataIndex: 'material_property_label', key: 'material_property_label', width: 80 },
    { title: 'MRP 数量', dataIndex: 'mrp_qty', key: 'mrp_qty', width: 100, align: 'right' as const, render: fmt },
    { title: '下单数量', dataIndex: 'po_qty', key: 'po_qty', width: 100, align: 'right' as const, render: fmt },
    { title: '已收', dataIndex: 'received_qty', key: 'received_qty', width: 100, align: 'right' as const, render: fmt },
    { title: '短缺', dataIndex: 'shortage_qty', key: 'shortage_qty', width: 100, align: 'right' as const, render: fmt },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (s: string, row: MaterialItem) => (
        <Tag color={MATERIAL_STATUS_COLOR[s] || 'default'}>{row.status_label || s}</Tag>
      ),
    },
  ]

  return (
    <div style={{ marginBottom: 8 }}>
      <Alert
        type="warning"
        showIcon
        message={`本订单有 ${orphans.length} 个物料未关联 BOM(MRP 计划有,BOM 未覆盖)`}
        action={
          <a onClick={() => setExpanded(v => !v)}>
            {expanded ? '收起' : '展开查看'} {expanded ? <UpOutlined /> : <DownOutlined />}
          </a>
        }
      />
      {expanded && (
        <Table<MaterialItem>
          rowKey="material_code"
          dataSource={orphans}
          columns={columns}
          size="small"
          pagination={false}
          scroll={{ x: 900, y: 240 }}
          style={{ marginTop: 8 }}
        />
      )}
    </div>
  )
}

export default OrphanMaterialAlert
