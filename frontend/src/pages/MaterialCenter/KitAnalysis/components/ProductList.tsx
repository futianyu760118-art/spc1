import React from 'react'
import { Progress, Tag } from 'antd'
import type { ProductKitSummary } from '../index'

const RISK_COLOR: Record<string, string> = { red: '#e11d48', yellow: '#f59e0b', green: '#16a34a' }
const RISK_LABEL: Record<string, string> = { red: '缺料严重', yellow: '部分齐套', green: '齐套' }

interface Props {
  products: ProductKitSummary[]
  selectedKey: string | null
  onSelect: (key: string) => void
  productKeys: string[]
}

const ProductList: React.FC<Props> = ({ products, selectedKey, onSelect, productKeys }) => {
  return (
    <div style={{ width: 240, flexShrink: 0, borderRight: '1px solid #f0f0f0', paddingRight: 8, overflowY: 'auto' }}>
      <div style={{ fontSize: 12, color: '#888', marginBottom: 8 }}>产品 ({products.length})</div>
      {products.map((p, idx) => {
        const key = productKeys[idx] ?? `${p.product_code}#${idx}`
        const selected = key === selectedKey
        return (
          <div
            key={key}
            onClick={() => onSelect(key)}
            style={{
              padding: '8px 10px',
              marginBottom: 6,
              borderRadius: 4,
              border: `1px solid ${selected ? '#91d5ff' : '#f0f0f0'}`,
              background: selected ? '#e6f7ff' : '#fff',
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 2 }}>
              {p.product_name || p.product_code || '(未命名产品)'}
              {!p.has_bom && <Tag color="default" style={{ marginLeft: 6 }}>无BOM</Tag>}
            </div>
            <div style={{ color: '#888', fontSize: 11 }}>
              {p.product_code} · 订单数 {p.order_qty ?? '-'} · {p.bom_no || '无BOM编号'}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', marginTop: 4 }}>
              <Progress
                percent={Math.round((p.kit_rate || 0) * 100)}
                size="small"
                strokeColor={RISK_COLOR[p.risk_level]}
                style={{ width: 100, marginBottom: 0, marginRight: 8 }}
                showInfo={false}
              />
              <span style={{ color: RISK_COLOR[p.risk_level], fontWeight: 600, fontSize: 12 }}>
                {Math.round((p.kit_rate || 0) * 100)}%
              </span>
              <Tag color={p.risk_level} style={{ marginLeft: 'auto' }}>{RISK_LABEL[p.risk_level]}</Tag>
            </div>
            <div style={{ color: '#888', fontSize: 11, marginTop: 2 }}>
              到齐 {p.leaf_received}/{p.leaf_total}
              {p.leaf_partial > 0 && ` · 部分 ${p.leaf_partial}`}
              {p.leaf_not_ordered > 0 && ` · 未下 ${p.leaf_not_ordered}`}
              {p.leaf_overdue > 0 && ` · 逾期 ${p.leaf_overdue}`}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default ProductList
