import React, { useEffect, useState, useCallback } from 'react'
import { Spin, Empty, message } from 'antd'
import { materialApi } from '@/services/api'
import type { BomKitFlatItem, OrderProductKitBreakdown } from '../index'
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
    breakdown && breakdown.products.length > 0
      ? `${breakdown.products[0].product_code || ''}#0`
      : null,
  )
  const [bomFlat, setBomFlat] = useState<BomKitFlatItem[]>([])
  const [bomFlatLoading, setBomFlatLoading] = useState(false)

  const loadBreakdown = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await materialApi.getOrderProductBreakdown(orderNo)
      onLoaded(res.data)
      const firstKey = res.data?.products?.length ? `${res.data.products[0].product_code || ''}#0` : null
      setSelectedKey(firstKey)
    } catch (e: any) {
      message.error(e.message || '加载产品齐套失败')
    } finally {
      setLoading(false)
    }
  }, [orderNo, onLoaded])

  useEffect(() => {
    if (!breakdown) {
      loadBreakdown()
    }
  }, [breakdown, loadBreakdown])

  const selectedProduct =
    breakdown && selectedKey
      ? breakdown.products.find(
          (p) => `${p.product_code || ''}#${breakdown.products.indexOf(p)}` === selectedKey,
        ) || null
      : null

  useEffect(() => {
    if (!breakdown || !selectedProduct || !selectedProduct.has_bom) {
      setBomFlat([])
      setBomFlatLoading(false)
      return
    }
    let cancelled = false
    setBomFlatLoading(true)
    materialApi
      .getOrderProductBomFlat(orderNo, selectedProduct.product_code || '')
      .then((res: any) => {
        if (!cancelled) {
          setBomFlat(res.data?.items || [])
        }
      })
      .catch((e: any) => {
        if (!cancelled) message.error(e.message || '加载 BOM 物料失败')
      })
      .finally(() => {
        if (!cancelled) setBomFlatLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [breakdown, selectedProduct, orderNo])

  if (loading) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Spin tip="加载产品齐套..." />
      </div>
    )
  }

  if (!breakdown) return null

  if (breakdown.products.length === 0 && breakdown.orphan_materials.length === 0) {
    return <Empty description="本订单无产品线与物料数据" style={{ padding: 24 }} />
  }

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
            ) : bomFlatLoading && bomFlat.length === 0 ? (
              <div style={{ padding: 24, textAlign: 'center' }}>
                <Spin tip="加载 BOM..." />
              </div>
            ) : (
              <BomMaterialTable items={bomFlat} loading={bomFlatLoading} />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default OrderProductKitPanel
