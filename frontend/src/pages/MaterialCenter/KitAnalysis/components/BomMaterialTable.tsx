import React, { useMemo } from 'react'
import { Table, Tag } from 'antd'
import type { BomKitMaterialItem } from '../index'

const MATERIAL_STATUS_COLOR: Record<string, string> = {
  not_in_plan: 'default',
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
  tree: BomKitMaterialItem[]
  loading?: boolean
}

const BomMaterialTable: React.FC<Props> = ({ tree, loading }) => {
  const columns = useMemo(() => [
    {
      title: '层级',
      dataIndex: 'level',
      key: 'level',
      width: 60,
      render: (lv: number) => `L${lv}`,
    },
    {
      title: '物料编码',
      dataIndex: 'material_code',
      key: 'material_code',
      width: 140,
    },
    {
      title: '物料名称',
      dataIndex: 'material_name',
      key: 'material_name',
      width: 160,
      render: (v: string | null) => v || <span style={{ color: '#ccc' }}>-</span>,
    },
    {
      title: '属性',
      dataIndex: 'material_property_label',
      key: 'material_property_label',
      width: 80,
    },
    {
      title: 'BOM 用量',
      dataIndex: 'standard_qty',
      key: 'standard_qty',
      width: 90,
      align: 'right' as const,
      render: fmt,
    },
    {
      title: '需求量',
      dataIndex: 'req_qty',
      key: 'req_qty',
      width: 90,
      align: 'right' as const,
      render: fmt,
    },
    {
      title: '即时库存',
      dataIndex: 'stock_qty',
      key: 'stock_qty',
      width: 90,
      align: 'right' as const,
      render: fmt,
    },
    {
      title: '在途',
      dataIndex: 'transit_qty',
      key: 'transit_qty',
      width: 80,
      align: 'right' as const,
      render: fmt,
    },
    {
      title: '已收',
      dataIndex: 'received_qty',
      key: 'received_qty',
      width: 90,
      align: 'right' as const,
      render: fmt,
    },
    {
      title: '短缺',
      dataIndex: 'shortage_qty',
      key: 'shortage_qty',
      width: 90,
      align: 'right' as const,
      render: (v: number | null) =>
        v != null && v > 0 ? <span style={{ color: '#cf1322', fontWeight: 600 }}>{fmt(v)}</span> : fmt(v),
    },
    {
      title: 'ETA',
      dataIndex: 'eta',
      key: 'eta',
      width: 100,
    },
    {
      title: '供应商',
      dataIndex: 'supplier_name',
      key: 'supplier_name',
      width: 120,
      render: (v: string | null) => v || <span style={{ color: '#ccc' }}>-</span>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (s: string, row: BomKitMaterialItem) => {
        if (s === 'not_in_plan') return <Tag>BOM 有 / 计划无</Tag>
        const label = row.status_label || s
        return <Tag color={MATERIAL_STATUS_COLOR[s] || 'default'}>{label}</Tag>
      },
    },
  ], [])

  return (
    <div style={{ flex: 1, minWidth: 0, paddingLeft: 12 }}>
      <div
        style={{
          background: '#e6f7ff',
          border: '1px solid #91d5ff',
          padding: '6px 10px',
          borderRadius: 4,
          fontSize: 12,
          color: '#0050b3',
          marginBottom: 8,
        }}
      >
        齐套数字为<b>订单级聚合</b>(来源 MRP/PO/库存),跨产品不累加;BOM 仅作结构展示
      </div>
      <Table<BomKitMaterialItem>
        rowKey={(r) => `${r.bom_id || ''}-${r.material_code || ''}-${r.level}`}
        dataSource={tree}
        columns={columns}
        size="small"
        pagination={false}
        loading={loading}
        scroll={{ x: 1300, y: 360 }}
        expandable={{
          childrenColumnName: 'children',
          defaultExpandAllRows: true,
          showExpandColumn: false,
        }}
      />
    </div>
  )
}

export default BomMaterialTable
