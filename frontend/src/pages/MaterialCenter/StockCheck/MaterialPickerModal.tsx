import { useEffect, useMemo, useState } from 'react'
import { Modal, Input, Table, Button, Space, message, Pagination, Spin, Tabs, Empty, Popconfirm } from 'antd'
import { SearchOutlined, ClearOutlined, PlusOutlined, DeleteOutlined } from '@ant-design/icons'
import { materialApi } from '@/services/api'
import { useStockCheckPoolStore, PoolMaterial } from '@/store/stockCheckPool'

interface MaterialCandidate {
  erp_material_id: number
  material_code?: string | null
  material_name?: string | null
  spec_model?: string | null
  unit?: string | null
  system_qty?: number | null
}

interface Props {
  open: boolean
  onCancel: () => void
  onConfirm: (selected: MaterialCandidate[], source: 'search' | 'pool') => void
  confirmLoading?: boolean
}

type TabKey = 'search' | 'pool'

export default function MaterialPickerModal({ open, onCancel, onConfirm, confirmLoading }: Props) {
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [items, setItems] = useState<MaterialCandidate[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [selectedMap, setSelectedMap] = useState<Record<number, MaterialCandidate>>({})

  const [activeTab, setActiveTab] = useState<TabKey>('search')
  const [poolSelectedIds, setPoolSelectedIds] = useState<number[]>([])

  const poolItems = useStockCheckPoolStore((s) => s.items)
  const poolAdd = useStockCheckPoolStore((s) => s.add)
  const poolRemove = useStockCheckPoolStore((s) => s.remove)
  const poolClear = useStockCheckPoolStore((s) => s.clear)
  const poolIdSet = useMemo(() => new Set(poolItems.map((p) => p.erp_material_id)), [poolItems])

  useEffect(() => {
    if (!open || activeTab !== 'search') return
    let cancelled = false
    setLoading(true)
    materialApi
      .listMaterialCandidates({ keyword: keyword || undefined, page, page_size: pageSize })
      .then((res: any) => {
        if (cancelled) return
        const data = res?.data || {}
        setItems((data.items || []) as MaterialCandidate[])
        setTotal(Number(data.total || 0))
      })
      .catch((err: any) => {
        if (!cancelled) message.error(err?.message || '加载物料候选失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, activeTab, keyword, page, pageSize])

  useEffect(() => {
    if (!open) {
      setSelectedIds(new Set())
      setSelectedMap({})
      setKeyword('')
      setPage(1)
      setActiveTab('search')
      setPoolSelectedIds([])
    }
  }, [open])

  const toggleRow = (row: MaterialCandidate) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(row.erp_material_id)) {
        next.delete(row.erp_material_id)
      } else {
        next.add(row.erp_material_id)
      }
      return next
    })
    setSelectedMap((prev) => {
      const next = { ...prev }
      if (selectedIds.has(row.erp_material_id)) {
        delete next[row.erp_material_id]
      } else {
        next[row.erp_material_id] = row
      }
      return next
    })
  }

  const togglePageAll = () => {
    const allSelected = items.length > 0 && items.every((it) => selectedIds.has(it.erp_material_id))
    setSelectedIds((prev) => {
      const next = new Set(prev)
      setSelectedMap((prevMap) => {
        const nextMap = { ...prevMap }
        items.forEach((it) => {
          if (allSelected) {
            next.delete(it.erp_material_id)
            delete nextMap[it.erp_material_id]
          } else {
            next.add(it.erp_material_id)
            nextMap[it.erp_material_id] = it
          }
        })
        return nextMap
      })
      return next
    })
  }

  const allOnPageSelected = useMemo(
    () => items.length > 0 && items.every((it) => selectedIds.has(it.erp_material_id)),
    [items, selectedIds],
  )

  const handleConfirm = () => {
    if (selectedIds.size === 0) {
      message.warning('请至少选择一个物料')
      return
    }
    onConfirm(Object.values(selectedMap), 'search')
  }

  const handleAddToPool = (rows: MaterialCandidate[]) => {
    if (rows.length === 0) return
    const poolMaterials: PoolMaterial[] = rows.map((r) => ({
      erp_material_id: r.erp_material_id,
      material_code: r.material_code ?? null,
      material_name: r.material_name ?? null,
      spec_model: r.spec_model ?? null,
      unit: r.unit ?? null,
      system_qty: r.system_qty ?? null,
      added_at: new Date().toISOString(),
    }))
    poolAdd(poolMaterials)
    message.success(`已加入待盘点池，当前共 ${useStockCheckPoolStore.getState().items.length} 项`)
  }

  const handleBatchAddToPool = () => {
    if (selectedIds.size === 0) {
      message.warning('请先勾选要加入待盘点池的物料')
      return
    }
    handleAddToPool(Object.values(selectedMap))
    setSelectedIds(new Set())
    setSelectedMap({})
  }

  const handlePoolCreate = () => {
    if (poolSelectedIds.length === 0) {
      message.warning('请至少选择一个物料')
      return
    }
    if (poolSelectedIds.length > 500) {
      message.warning('一次最多创建 500 个物料的盘点单，请减少勾选数量')
      return
    }
    const selected: MaterialCandidate[] = poolSelectedIds.map((id) => {
      const row = poolItems.find((p) => p.erp_material_id === id)
      return {
        erp_material_id: id,
        material_code: row?.material_code ?? null,
        material_name: row?.material_name ?? null,
        spec_model: row?.spec_model ?? null,
        unit: row?.unit ?? null,
        system_qty: row?.system_qty ?? null,
      }
    })
    onConfirm(selected, 'pool')
  }

  const searchColumns = [
    {
      title: (
        <input
          type="checkbox"
          checked={allOnPageSelected}
          onChange={togglePageAll}
          style={{ cursor: 'pointer' }}
        />
      ),
      key: 'select',
      width: 48,
      render: (_: any, row: MaterialCandidate) => (
        <input
          type="checkbox"
          checked={selectedIds.has(row.erp_material_id)}
          onChange={() => toggleRow(row)}
          style={{ cursor: 'pointer' }}
        />
      ),
    },
    { title: '物料编码', dataIndex: 'material_code', key: 'material_code', width: 140 },
    { title: '物料名称', dataIndex: 'material_name', key: 'material_name', width: 180, ellipsis: true },
    { title: '规格', dataIndex: 'spec_model', key: 'spec_model', width: 160, ellipsis: true },
    { title: '单位', dataIndex: 'unit', key: 'unit', width: 70 },
    {
      title: '即时库存',
      dataIndex: 'system_qty',
      key: 'system_qty',
      width: 100,
      align: 'right' as const,
      render: (v: number | null | undefined) => (v == null ? '—' : Number(v).toFixed(2)),
    },
    {
      title: '操作',
      key: 'action',
      width: 130,
      fixed: 'right' as const,
      render: (_: any, row: MaterialCandidate) => {
        const inPool = poolIdSet.has(row.erp_material_id)
        return (
          <Button
            size="small"
            type={inPool ? 'default' : 'link'}
            icon={<PlusOutlined />}
            disabled={inPool}
            onClick={() => handleAddToPool([row])}
          >
            {inPool ? '已在池中' : '加入待盘点池'}
          </Button>
        )
      },
    },
  ]

  const poolColumns = [
    { title: '物料编码', dataIndex: 'material_code', key: 'material_code', width: 140 },
    { title: '物料名称', dataIndex: 'material_name', key: 'material_name', width: 180, ellipsis: true },
    { title: '规格', dataIndex: 'spec_model', key: 'spec_model', width: 160, ellipsis: true },
    { title: '单位', dataIndex: 'unit', key: 'unit', width: 70 },
    {
      title: '即时库存(快照)',
      dataIndex: 'system_qty',
      key: 'system_qty',
      width: 130,
      align: 'right' as const,
      render: (v: number | null | undefined) => (v == null ? '—' : Number(v).toFixed(2)),
    },
    {
      title: '加入时间',
      dataIndex: 'added_at',
      key: 'added_at',
      width: 160,
      render: (v: string) => (v ? new Date(v).toLocaleString() : '—'),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      fixed: 'right' as const,
      render: (_: any, row: PoolMaterial) => (
        <Button
          size="small"
          type="link"
          danger
          icon={<DeleteOutlined />}
          onClick={() => {
            poolRemove([row.erp_material_id])
            setPoolSelectedIds((prev) => prev.filter((id) => id !== row.erp_material_id))
          }}
        >
          移除
        </Button>
      ),
    },
  ]

  const searchTab = (
    <>
      <Space style={{ marginBottom: 12 }} size="middle">
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="搜索物料编码/名称/规格"
          value={keyword}
          onChange={(e) => {
            setKeyword(e.target.value)
            setPage(1)
          }}
          style={{ width: 280 }}
        />
        <Button icon={<ClearOutlined />} onClick={() => { setKeyword(''); setPage(1) }}>
          清空
        </Button>
      </Space>
      <Spin spinning={loading}>
        <Table
          rowKey="erp_material_id"
          size="small"
          dataSource={items}
          columns={searchColumns as any}
          pagination={false}
          scroll={{ y: 360 }}
        />
      </Spin>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
        <Pagination
          current={page}
          pageSize={pageSize}
          total={total}
          showSizeChanger
          pageSizeOptions={['10', '20', '50', '100']}
          onChange={(p, ps) => { setPage(p); setPageSize(ps) }}
          showTotal={(t) => `共 ${t} 项`}
        />
      </div>
    </>
  )

  const poolTab =
    poolItems.length === 0 ? (
      <Empty description="待盘点池为空，请到「搜索物料」标签添加物料" />
    ) : (
      <Table
        rowKey="erp_material_id"
        size="small"
        dataSource={poolItems}
        columns={poolColumns as any}
        pagination={false}
        scroll={{ y: 360 }}
        rowSelection={{
          selectedRowKeys: poolSelectedIds,
          onChange: (keys) => setPoolSelectedIds(keys as number[]),
          preserveSelectedRowKeys: true,
        }}
      />
    )

  const searchFooter = (
    <Space style={{ width: '100%', justifyContent: 'space-between' }}>
      <span>
        已选 <b style={{ color: '#1677ff' }}>{selectedIds.size}</b> 项
      </span>
      <Space>
        <Button onClick={onCancel}>取消</Button>
        <Button onClick={handleBatchAddToPool}>加入待盘点池(已选{selectedIds.size}项)</Button>
        <Button type="primary" loading={confirmLoading} onClick={handleConfirm}>
          确定并创建盘点单
        </Button>
      </Space>
    </Space>
  )

  const poolFooter = (
    <Space style={{ width: '100%', justifyContent: 'space-between' }}>
      <span>
        待盘点池共 <b style={{ color: '#1677ff' }}>{poolItems.length}</b> 项，已选{' '}
        <b style={{ color: '#1677ff' }}>{poolSelectedIds.length}</b> 项
      </span>
      <Space>
        <Button
          disabled={poolSelectedIds.length === 0}
          onClick={() => {
            poolRemove(poolSelectedIds)
            setPoolSelectedIds([])
          }}
        >
          移除选中
        </Button>
        <Popconfirm
          title="确定清空待盘点池？"
          okText="确定"
          cancelText="取消"
          onConfirm={() => {
            poolClear()
            setPoolSelectedIds([])
          }}
        >
          <Button disabled={poolItems.length === 0}>清空</Button>
        </Popconfirm>
        <Button onClick={onCancel}>取消</Button>
        <Button type="primary" loading={confirmLoading} onClick={handlePoolCreate}>
          创建盘点单(已选{poolSelectedIds.length}项)
        </Button>
      </Space>
    </Space>
  )

  return (
    <Modal
      title="选择盘点物料"
      open={open}
      onCancel={onCancel}
      width={900}
      destroyOnClose
      footer={activeTab === 'search' ? searchFooter : poolFooter}
    >
      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as TabKey)}
        items={[
          { key: 'search', label: '搜索物料', children: searchTab },
          {
            key: 'pool',
            label: (
              <span data-tour="stock-check-pool-tab">
                待盘点池 ({poolItems.length})
              </span>
            ),
            children: poolTab,
          },
        ]}
      />
    </Modal>
  )
}
