import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Button, Card, Col, Input, InputNumber, message, Modal, Row, Space, Spin,
  Statistic, Table, Tag, Tooltip, Typography,
} from 'antd'
import type { InputRef } from 'antd'
import { ArrowLeftOutlined, SearchOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { materialApi } from '@/services/api'

interface Candidate {
  erp_material_id: number
  material_code?: string | null
  material_name?: string | null
  spec_model?: string | null
  unit?: string | null
  system_qty?: number | null
  wh_id?: number | null
  wh_code?: string | null
  wh_name?: string | null
  recent_checked_check_no?: string | null
  recent_checked_date?: string | null
}

interface TodayItem {
  id: number
  material_id: number | null
  material_code?: string | null
  material_name?: string | null
  spec_model?: string | null
  unit?: string | null
  wh_id?: number | null
  wh_name?: string | null
  system_qty: number
  actual_qty: number | null
  diff_qty: number
  counted_by?: string | null
  counted_at?: string | null
}

interface TodaySheet {
  check_id: number
  check_no: string
  title: string
  items: TodayItem[]
}

export default function QuickCount() {
  const navigate = useNavigate()

  // ===== 搜索(输入即搜,防抖 300ms;回车立即搜索=扫码枪模式) =====
  const [keyword, setKeyword] = useState('')
  const [results, setResults] = useState<Candidate[]>([])
  const [searching, setSearching] = useState(false)
  const [searched, setSearched] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inputRef = useRef<InputRef>(null)
  // 最近一次搜索是否由回车触发(扫码枪): 保存后清空+重新聚焦,支持连续扫码
  const lastSearchByEnter = useRef(false)

  const doSearch = useCallback(async (kw: string) => {
    const q = kw.trim()
    if (!q) { setResults([]); setSearched(false); return }
    setSearching(true)
    setSearched(true)
    try {
      const res: any = await materialApi.listMaterialCandidates({ keyword: q, page: 1, page_size: 20 })
      setResults(res.data?.items || [])
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '搜索物料失败')
    } finally {
      setSearching(false)
    }
  }, [])

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => doSearch(keyword), 300)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [keyword]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSearchEnter = useCallback(() => {
    // 回车=立即搜索(不等待防抖),并离开输入框 → 后续数字键 1/2/3 触发快捷盘点
    if (debounceRef.current) clearTimeout(debounceRef.current)
    lastSearchByEnter.current = true
    doSearch(keyword)
    inputRef.current?.blur()
  }, [keyword, doSearch])

  // ===== 今日已录 =====
  const [today, setToday] = useState<TodaySheet | null>(null)
  const [todayLoading, setTodayLoading] = useState(false)

  const loadToday = useCallback(async () => {
    setTodayLoading(true)
    try {
      const res: any = await materialApi.getTodayQuickCheck()
      setToday(res.data || null)
    } catch {
      /* 静默 */
    } finally {
      setTodayLoading(false)
    }
  }, [])

  useEffect(() => { loadToday() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ===== 盘平/盘盈/盘亏 =====
  const [modal, setModal] = useState<{ row: Candidate | TodayItem; action: 'surplus' | 'deficit' } | null>(null)
  const [modalQty, setModalQty] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)

  const doCount = useCallback(async (row: Candidate | TodayItem, actualQty: number) => {
    setSaving(true)
    try {
      const mid = 'erp_material_id' in row ? row.erp_material_id : row.material_id
      const res: any = await materialApi.quickCountStockCheck({
        material_id: mid!,
        wh_id: row.wh_id ?? null,
        actual_qty: actualQty,
      })
      const d = res.data || {}
      message.success(`已录入 ${d.check_no}：${d.item?.material_code ?? ''} 实盘 ${d.item?.actual_qty} 差异 ${d.item?.diff_qty}`)
      await loadToday()
      // 扫码模式(回车搜索): 清空并重新聚焦,直接扫下一件
      if (lastSearchByEnter.current) {
        lastSearchByEnter.current = false
        setKeyword('')
        setTimeout(() => inputRef.current?.focus(), 50)
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '快捷盘点失败')
    } finally {
      setSaving(false)
    }
  }, [loadToday])

  const openModal = useCallback((row: Candidate | TodayItem, action: 'surplus' | 'deficit') => {
    setModalQty(row.system_qty != null ? Number(row.system_qty) : null)
    setModal({ row, action })
  }, [])

  // 键盘快捷键: 搜索结果存在且未在输入时,1=盘平 2=盘盈 3=盘亏(作用于第一行)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (modal || saving || results.length === 0) return
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      const first = results[0]
      if (e.key === '1') {
        e.preventDefault()
        if (first.system_qty != null) doCount(first, sysOf(first) ?? 0)
      } else if (e.key === '2') {
        e.preventDefault()
        openModal(first, 'surplus')
      } else if (e.key === '3') {
        e.preventDefault()
        openModal(first, 'deficit')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [modal, saving, results, doCount, openModal])

  const confirmModal = useCallback(async () => {
    if (!modal) return
    const sys = modal.row.system_qty != null ? Number(modal.row.system_qty) : null
    if (modalQty == null || sys == null) { message.warning('请输入实盘数'); return }
    if (modal.action === 'surplus' && modalQty <= sys) { message.warning(`盘盈要求实盘数大于库存数 ${sys}`); return }
    if (modal.action === 'deficit' && modalQty >= sys) { message.warning(`盘亏要求实盘数小于库存数 ${sys}`); return }
    const ctx = { ...modal }
    setModal(null)
    await doCount(ctx.row, modalQty)
  }, [modal, modalQty, doCount])

  const sysOf = (r: Candidate | TodayItem) => r.system_qty != null ? Number(r.system_qty) : null

  const actionButtons = (r: Candidate | TodayItem) => (
    <Space size="small">
      <Button
        type="link" size="small" style={{ padding: 0 }} disabled={saving || r.system_qty == null}
        onClick={() => doCount(r, sysOf(r) ?? 0)}
      >盘平</Button>
      <Button
        type="link" size="small" style={{ padding: 0 }} disabled={saving}
        onClick={() => openModal(r, 'surplus')}
      >盘盈</Button>
      <Button
        type="link" size="small" style={{ padding: 0, color: '#dc2626' }} disabled={saving}
        onClick={() => openModal(r, 'deficit')}
      >盘亏</Button>
    </Space>
  )

  const searchColumns = [
    { title: '物料编码', dataIndex: 'material_code', width: 150 },
    { title: '物料名称', dataIndex: 'material_name', ellipsis: true },
    { title: '规格型号', dataIndex: 'spec_model', width: 150, ellipsis: true, render: (v: any) => v || '—' },
    { title: '仓库', dataIndex: 'wh_name', width: 110 },
    {
      title: '库存数', dataIndex: 'system_qty', width: 110, align: 'right' as const,
      render: (v: any) => v == null ? '—' : Number(v).toFixed(2),
    },
    ...(results.some((r) => r.recent_checked_check_no) ? [{
      title: '近盘', dataIndex: 'recent_checked_check_no', width: 90,
      render: (v: any, r: Candidate) => v ? (
        <Tooltip title={`近期已盘 ${v}${r.recent_checked_date ? ' · ' + r.recent_checked_date : ''}`}>
          <Tag color="default" style={{ marginInlineEnd: 0 }}>已盘</Tag>
        </Tooltip>
      ) : null,
    }] : []),
    { title: '快捷盘点', key: 'op', width: 200, render: (_: any, r: Candidate) => actionButtons(r) },
  ]

  const todayItems = today?.items ?? []
  const stats = {
    even: todayItems.filter((it) => Number(it.diff_qty) === 0).length,
    surplus: todayItems.filter((it) => Number(it.diff_qty) > 0).length,
    deficit: todayItems.filter((it) => Number(it.diff_qty) < 0).length,
  }

  const todayColumns = [
    { title: '物料编码', dataIndex: 'material_code', width: 150 },
    { title: '物料名称', dataIndex: 'material_name', ellipsis: true },
    { title: '仓库', dataIndex: 'wh_name', width: 110 },
    {
      title: '库存数', dataIndex: 'system_qty', width: 100, align: 'right' as const,
      render: (v: any) => Number(v || 0).toFixed(2),
    },
    {
      title: '实盘数', dataIndex: 'actual_qty', width: 100, align: 'right' as const,
      render: (v: any) => v == null ? '—' : Number(v).toFixed(2),
    },
    {
      title: '差异', dataIndex: 'diff_qty', width: 100, align: 'right' as const,
      render: (v: any) => {
        const n = Number(v || 0)
        const color = n > 0 ? '#16a34a' : n < 0 ? '#dc2626' : '#64748b'
        return <span style={{ color, fontWeight: 500 }}>{n.toFixed(2)}</span>
      },
    },
    {
      title: '结果', key: 'result', width: 80,
      render: (_: any, r: TodayItem) => {
        const n = Number(r.diff_qty || 0)
        if (n === 0) return <Tag style={{ marginInlineEnd: 0 }}>平</Tag>
        if (n > 0) return <Tag color="green" style={{ marginInlineEnd: 0 }}>盈</Tag>
        return <Tag color="red" style={{ marginInlineEnd: 0 }}>亏</Tag>
      },
    },
    {
      title: '录入时间', dataIndex: 'counted_at', width: 150,
      render: (v: string) => (v ? new Date(v).toLocaleString('zh-CN', { hour12: false }) : '—'),
    },
    { title: '重录', key: 'op', width: 200, render: (_: any, r: TodayItem) => actionButtons(r) },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Space wrap style={{ marginBottom: 12 }}>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/stock-check')}>返回物料盘点</Button>
          <Typography.Title level={4} style={{ margin: 0 }}>
            <ThunderboltOutlined style={{ color: '#faad14', marginRight: 6 }} />快捷盘点
          </Typography.Title>
          <Typography.Text type="secondary">搜物料直接盘平 / 盘盈 / 盘亏，自动记入当日快捷盘点单</Typography.Text>
        </Space>
        <Input
          ref={inputRef}
          size="large"
          autoFocus
          placeholder="扫码 / 输入物料编码·名称·规格，回车立即搜索；结果出来后按 1=盘平 2=盘盈 3=盘亏"
          value={keyword}
          onChange={(e) => { lastSearchByEnter.current = false; setKeyword(e.target.value) }}
          onPressEnter={handleSearchEnter}
          allowClear
          prefix={<SearchOutlined />}
        />
        {results.length > 0 && (
          <div style={{ marginTop: 8, padding: '4px 12px', background: '#f6ffed', border: '1px solid #b7eb8f', borderRadius: 6, fontSize: 12, color: '#389e0d' }}>
            第一行 <b>{results[0].material_code}</b>（{results[0].wh_name}）：按
            <b> 1 </b>盘平 · <b> 2 </b>盘盈 · <b> 3 </b>盘亏；扫码模式下保存后自动聚焦继续扫下一件
          </div>
        )}
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px', marginBottom: 16 }}>
        <Spin spinning={searching}>
          <Table
            size="small"
            rowKey={(r) => `${r.erp_material_id}-${r.wh_id ?? 'none'}`}
            dataSource={results}
            columns={searchColumns as any}
            pagination={false}
            scroll={{ y: 320 }}
            locale={{ emptyText: searched ? '无匹配物料' : '输入关键词搜索物料' }}
            style={{ padding: 8 }}
          />
        </Spin>
      </div>

      <Row gutter={16}>
        <Col xs={24} md={6}>
          <Card size="small" className="card-modern">
            <Statistic title="今日盘平" value={stats.even} suffix="项" />
            <Statistic title="今日盘盈" value={stats.surplus} suffix="项" valueStyle={{ color: '#16a34a' }} />
            <Statistic title="今日盘亏" value={stats.deficit} suffix="项" valueStyle={{ color: '#dc2626' }} />
            {today && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                单号 {today.check_no}
              </Typography.Text>
            )}
          </Card>
        </Col>
        <Col xs={24} md={18}>
          <div className="card-modern" style={{ padding: '0 0 4px' }}>
            <Table
              size="small"
              rowKey="id"
              dataSource={todayItems}
              columns={todayColumns as any}
              pagination={false}
              loading={todayLoading}
              scroll={{ y: 320 }}
              locale={{ emptyText: '今日暂无快捷盘点记录' }}
              style={{ padding: 8 }}
              title={() => (
                <span style={{ fontWeight: 600 }}>今日已录（重复录入会覆盖上次结果）</span>
              )}
            />
          </div>
        </Col>
      </Row>

      <Modal
        open={!!modal}
        title={modal?.action === 'surplus' ? '盘盈 — 录入实盘数' : '盘亏 — 录入实盘数'}
        okText="保存"
        cancelText="取消"
        confirmLoading={saving}
        onOk={confirmModal}
        onCancel={() => setModal(null)}
        destroyOnClose
      >
        {modal && (
          <div>
            <p style={{ marginBottom: 8 }}>
              {modal.row.material_code} · {modal.row.material_name} · {modal.row.wh_name}
            </p>
            <p style={{ marginBottom: 8, color: '#64748b' }}>
              库存数 {modal.row.system_qty != null ? Number(modal.row.system_qty) : '—'}
              {modal.action === 'surplus' ? '，实盘数需大于库存数（盘盈）' : '，实盘数需小于库存数（盘亏）'}
            </p>
            <InputNumber
              min={0}
              step={0.01}
              value={modalQty}
              onChange={(v) => setModalQty(v == null ? null : Number(v))}
              onPressEnter={confirmModal}
              style={{ width: 200 }}
              addonAfter="实盘数"
              autoFocus
              onFocus={(e) => e.target.select()}
            />
          </div>
        )}
      </Modal>
    </div>
  )
}
