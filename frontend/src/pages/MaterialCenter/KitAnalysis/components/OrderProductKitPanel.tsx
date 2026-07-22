import React, { useEffect, useState, useCallback } from 'react'
import { Spin, Empty, message } from 'antd'
import { materialApi } from '@/services/api'
import type { OrderProductKitBreakdown } from '../index'
import ProductList from './ProductList'
import BomMaterialTable from './BomMaterialTable'
import OrphanMaterialAlert from './OrphanMaterialAlert'

interface Props {
  orderNo: string
  breakdown: OrderProductKitBreakdown | null
  onLoaded: (data: OrderProductKitBreakdown) => void
}

const OrderProductKitPanel: React.FC<Props> = ({ orderNo, breakdown, onLoaded }) => {
  const [loading, setLoading] = useState(!breakdown)
  const [selectedKey, setSelectedKey] = useState<string | null>(
    breakdown && breakdown.products.length > 0 ? `${breakdown.products[0].product_code}#0` : null,
  )

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await materialApi.getOrderProductBreakdown(orderNo)
      onLoaded(res.data)
      const firstKey = res.data?.products?.length ? `${res.data.products[0].product_code}#0` : null
      setSelectedKey(firstKey)
    } catch (e: any) {
      message.error(e.message || '加载产品齐套失败')
    } finally {
      setLoading(false)
    }
  }, [orderNo, onLoaded])

  useEffect(() => {
    if (!breakdown) {
      load()
    }
  }, [breakdown, load])

  if (loading) {
    return <div style={{ padding: 24, textAlign: 'center' }}><Spin tip="加载产品齐套..." /></div>
  }

  if (!breakdown) return null

  if (breakdown.products.length === 0 && breakdown.orphan_materials.length === 0) {
    return <Empty description="本订单无产品线与物料数据" style={{ padding: 24 }} />
  }

  const productKeys = breakdown.products.map((p, idx) => `${p.product_code}#${idx}`)
  const selectedIdx = productKeys.indexOf(selectedKey || '')
  const selectedProduct = selectedIdx >= 0 ? breakdown.products[selectedIdx] : null
  const selectedTree = selectedIdx >= 0
    ? (breakdown.bom_trees[productKeys[selectedIdx]] || [])
    : []

  return (
    <div style={{ padding: '8px 12px 16px 36px' }}>
      <OrphanMaterialAlert orphans={breakdown.orphan_materials} />
      {breakdown.products.length === 0 ? (
        <div style={{ color: '#888', fontSize: 13, padding: 12 }}>
          本订单无产品线数据(SaleOrderLine 为空)
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 12 }}>
          <ProductList
            products={breakdown.products}
            selectedKey={selectedKey}
            onSelect={setSelectedKey}
            productKeys={productKeys}
          />
          <div style={{ flex: 1, minWidth: 0 }}>
            {selectedProduct && (
              <div style={{ marginBottom: 8, fontSize: 13 }}>
                <b>BOM 物料齐套 — {selectedProduct.product_name || selectedProduct.product_code}</b>
                {' '}
                (BOM: {selectedProduct.bom_no || selectedProduct.bom_id || '-'})
                · 订单数 {selectedProduct.order_qty ?? '-'}
              </div>
            )}
            {selectedProduct && !selectedProduct.has_bom ? (
              <Empty description="该产品未关联 BOM,无物料树可展开" style={{ padding: 24 }} />
            ) : (
              <BomMaterialTable tree={selectedTree} />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default OrderProductKitPanel
