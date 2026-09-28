import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, DatePicker, Input, InputNumber, Modal, Select, Table, Tooltip, message } from 'antd'
import { DeleteOutlined, ExportOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import type { ColumnsType } from 'antd/es/table'
import { materialApi } from '../../../services/api'
import { useAuthStore } from '../../../store/auth'
import { useExport } from '../../../hooks/useExport'
import { formatDateTime } from '../../../utils'
import {
  REQUISITION_SOURCE_MAP, REQUISITION_STATUS_MAP,
  type Requisition, type RequisitionLine,
} from '../../../components/PurchaseRequisitionPaper'

type EditorLine = {
  key: number
  material_code: string
  req_qty: number | null
  need_date: Dayjs | null
  remark: string
}

/** 新建 / 编辑申请单共用弹窗（编辑时整单明细替换）——列表与详情共用。 */
export function RequisitionEditorModal({ open, editId, onClose, onSaved }: {
  open: boolean
  editId?: number | null
  onClose: () => void
  onSaved?: (id?: number) => void
}) {
  const keyRef = useRef(0)
  const makeLine = (): EditorLine => ({ key: ++keyRef.current, material_code: '', req_qty: null, need_date: null, remark: '' })
  const [department, setDepartment] = useState('')
  const [remark, setRemark] = useState('')
  const [lines, setLines] = useState<EditorLine[]>([makeLine()])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    if (!editId) {
      setDepartment('')
      setRemark('')
      setLines([makeLine()])
      return
    }
    setLoading(true)
    ;(async () => {
      try {
        const res: any = await materialApi.getPurchaseRequisition(editId)
        const d = res.data || {}
        setDepartment(d.department || '')
        setRemark(d.remark || '')
        const ls: EditorLine[] = (d.lines || []).map((l: RequisitionLine) => ({
          key: ++keyRef.current,
          material_code: l.material_code || '',
          req_qty: l.req_qty ?? null,
          need_date: l.need_date ? dayjs(l.need_date) : null,
          remark: l.remark || '',
        }))
        setLines(ls.length ? ls : [makeLine()])
      } catch (e: any) {
        message.error(e?.response?.data?.detail || '加载申请单明细失败')
        onClose()
      } finally { setLoading(false) }
    })()
  }, [open, editId]) // eslint-disable-line react-hooks/exhaustive-deps

  const updateLine = (key: number, patch: Partial<EditorLine>) =>
    setLines(prev => prev.map(l => (l.key === key ? { ...l, ...patch } : l)))

  const save = async () => {
    if (lines.length === 0) { message.warning('请至少添加一行明细'); return }
    for (let i = 0; i < lines.length; i++) {
      if (!lines[i].material_code.trim()) { message.warning(`第 ${i + 1} 行物料编码不能为空`); return }
      if (!lines[i].req_qty || Number(lines[i].req_qty) <= 0) { message.warning(`第 ${i + 1} 行数量必须大于 0`); return }
    }
    const payload = {
      department: department.trim() || null,
      remark: remark.trim() || null,
      lines: lines.map(l => ({
        material_code: l.material_code.trim(),
        req_qty: Number(l.req_qty),
        need_date: l.need_date ? l.need_date.format('YYYY-MM-DD') : null,
        remark: l.remark.trim() || null,
      })),
    }
    setSaving(true)
    try {
      const res: any = editId
        ? await materialApi.updatePurchaseRequisition(editId, payload)
        : await materialApi.createPurchaseRequisition(payload)
      message.success(res.message || '保存成功')
      onSaved?.(res.data?.id)
      onClose()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '保存失败')
    } finally { setSaving(false) }
  }

  const lineColumns: ColumnsType<EditorLine> = [
    {
      title: '物料编码', dataIndex: 'material_code', width: 190,
      render: (v: string, l) => (
        <Input value={v} placeholder="输入物料编码" onChange={e => updateLine(l.key, { material_code: e.target.value })} />
      ),
    },
    {
      title: '数量', dataIndex: 'req_qty', width: 130,
      render: (v: number | null, l) => (
        <InputNumber value={v} min={0} precision={4} style={{ width: '100%' }} placeholder="0"
          onChange={val => updateLine(l.key, { req_qty: val })} />
      ),
    },
    {
      title: '到货日期', dataIndex: 'need_date', width: 150,
      render: (v: Dayjs | null, l) => (
        <DatePicker value={v} style={{ width: '100%' }} onChange={d => updateLine(l.key, { need_date: d })} />
      ),
    },
    {
      title: '备注', dataIndex: 'remark',
      render: (v: string, l) => (
        <Input value={v} placeholder="选填" onChange={e => updateLine(l.key, { remark: e.target.value })} />
      ),
    },
    {
      title: '', width: 46, align: 'center',
      render: (_: any, l) => (
        <Button type="text" danger icon={<DeleteOutlined />} disabled={lines.length <= 1}
          onClick={() => setLines(prev => prev.filter(x => x.key !== l.key))} />
      ),
    },
  ]

  return (
    <Modal title={editId ? '编辑采购申请单' : '新建采购申请单'} open={open} width={880}
      okText="保存" confirmLoading={saving || loading} onOk={save} onCancel={onClose} maskClosable={false}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
        <div>
          <div className="sc-note" style={{ marginBottom: 6 }}>部门（选填）</div>
          <Input value={department} onChange={e => setDepartment(e.target.value)} placeholder="如采购部" />
        </div>
        <div>
          <div className="sc-note" style={{ marginBottom: 6 }}>备注（选填）</div>
          <Input value={remark} onChange={e => setRemark(e.target.value)} placeholder="整单备注" />
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', margin: '14px 0 8px' }}>
        <b style={{ fontSize: 13 }}>申请明细</b>
        <span className="sc-note" style={{ marginLeft: 8 }}>物料编码须存在于基础物料；保存时整单明细替换</span>
        <Button size="small" type="link" icon={<PlusOutlined />} style={{ marginLeft: 'auto' }}
          onClick={() => setLines(prev => [...prev, makeLine()])}>添加行</Button>
      </div>
      <Table<EditorLine> rowKey="key" size="small" pagination={false} columns={lineColumns}
        dataSource={lines} scroll={{ y: 300 }} loading={loading} />
    </Modal>
  )
}

export default function PurchaseRequisitionList() {
  const navigate = useNavigate()
  const hasPermission = useAuthStore((s) => s.hasPermission) as (resource: string, action: string) => boolean
  const canCreate = hasPermission('materials.purchase_requisition', 'create')
  const { exporting, exportData } = useExport()

  const [items, setItems] = useState<Requisition[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState('')
  const [applicant, setApplicant] = useState('')
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setSelectedId(null)
    try {
      const res: any = await materialApi.listPurchaseRequisitions({
        page, page_size: 20,
        keyword: keyword || undefined,
        status: status || undefined,
        applicant: applicant.trim() || undefined,
        date_start: range?.[0]?.format('YYYY-MM-DD'),
        date_end: range?.[1]?.format('YYYY-MM-DD'),
      })
      const data = res.data || {}
      if (page > 1 && (data.items || []).length === 0 && data.total > 0) { setPage(page - 1); return }
      setItems(data.items || [])
      setTotal(data.total || 0)
    } catch { /* 全局拦截器已提示 */ } finally { setLoading(false) }
  }, [page, keyword, status, applicant, range])
  useEffect(() => { load() }, [load])

  const exportTarget = items.find(i => i.id === selectedId)
  const doExport = () => {
    if (!exportTarget) { message.warning('请先勾选一张申请单再导出'); return }
    exportData(`/api/v1/materials/purchase-requisitions/${exportTarget.id}/export`, { format: 'csv' },
      `${exportTarget.req_no}-采购申请单.csv`)
  }

  const columns: ColumnsType<Requisition> = [
    {
      title: '申请单号', dataIndex: 'req_no', width: 160, fixed: 'left',
      render: (v: string, r) => (
        <a className="sc-mono" style={{ fontWeight: 600 }} onClick={() => navigate(`/purchase-requisitions/${r.id}`)}>{v}</a>
      ),
    },
    {
      title: '状态', dataIndex: 'status', width: 92,
      render: (v: string) => {
        const s = REQUISITION_STATUS_MAP[v] || { text: v, cls: 'sc-tag-plain' }
        return <span className={`sc-tag ${s.cls}`}><span className="dot" />{s.text}</span>
      },
    },
    { title: '申请人', dataIndex: 'applicant', width: 104, ellipsis: true, render: (v: string) => v || '-' },
    {
      title: '来源', dataIndex: 'source', width: 84,
      render: (v: string) => {
        const s = REQUISITION_SOURCE_MAP[v] || { text: v || '-', cls: 'sc-tag-plain' }
        return <span className={`sc-tag ${s.cls}`}>{s.text}</span>
      },
    },
    {
      title: '行数', dataIndex: 'line_count', width: 68, align: 'right',
      render: (v: number) => <span className="sc-mono">{v ?? 0}</span>,
    },
    {
      title: '提交时间', dataIndex: 'submitted_at', width: 140,
      render: (v: string) => <span className="sc-mono">{v ? formatDateTime(v) : '-'}</span>,
    },
    {
      title: '审批人', width: 160, ellipsis: true,
      render: (_: any, r) => {
        if (r.status === 'approved') return r.approved_by || '-'
        if (r.status !== 'approving') return '-'
        const node: any = (r.approval_snapshot || []).find((n: any) => n.seq === r.approval_level)
        if (!node) return <span className="sc-note">-</span>
        const approvers = Array.isArray(node.approvers)
          ? node.approvers.map((a: any) => a.username || String(a.user_id || '')).filter(Boolean).join('、')
          : node.role || ''
        return <span>{node.label || '-'}{approvers ? <span className="sc-note"> · {approvers}</span> : null}</span>
      },
    },
    {
      title: '操作', width: 72, fixed: 'right',
      render: (_: any, r) => (
        <Button size="small" type="link" onClick={() => navigate(`/purchase-requisitions/${r.id}`)}>查看</Button>
      ),
    },
  ]

  return (
    <div className="sc-page">
      <div className="card-modern" style={{ padding: '14px 18px', marginBottom: 12 }}>
        <div className="sc-toolbar" style={{ marginBottom: 0 }}>
          <Input.Search allowClear style={{ width: 230 }} placeholder="申请单号 / 申请人"
            onSearch={v => { setPage(1); setKeyword(v) }} />
          <Select allowClear placeholder="单据状态" style={{ width: 116 }} value={status || undefined}
            onChange={v => { setPage(1); setStatus(v || '') }}
            options={Object.entries(REQUISITION_STATUS_MAP).map(([value, s]) => ({ value, label: s.text }))} />
          <Input allowClear placeholder="申请人" style={{ width: 120 }} value={applicant}
            onChange={e => setApplicant(e.target.value)}
            onPressEnter={() => setPage(1)}
            onBlur={() => setPage(1)} />
          <DatePicker.RangePicker value={range} onChange={v => { setRange(v); setPage(1) }} />
          <Button icon={<ReloadOutlined />} onClick={load} />
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            <Tooltip title={exportTarget ? `导出 ${exportTarget.req_no} 明细 CSV` : '勾选一张申请单后可导出明细'}>
              <Button icon={<ExportOutlined />} loading={exporting} disabled={!exportTarget} onClick={doExport}>导出</Button>
            </Tooltip>
            {canCreate && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setEditorOpen(true)}>新建</Button>
            )}
          </div>
        </div>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table<Requisition>
          rowKey="id" loading={loading} dataSource={items} columns={columns}
          scroll={{ x: 1000 }} size="middle"
          rowSelection={{
            type: 'radio',
            selectedRowKeys: selectedId != null ? [selectedId] : [],
            onChange: keys => setSelectedId(keys.length ? Number(keys[0]) : null),
          }}
          onRow={r => ({
            style: { cursor: 'pointer' },
            onClick: e => {
              const el = e.target as HTMLElement
              if (el.closest('input,button,a,label')) return
              navigate(`/purchase-requisitions/${r.id}`)
            },
          })}
          locale={{ emptyText: '暂无采购申请单——点击右上角「新建」手工建单，或在 MRP 建议列表勾选后转单' }}
          pagination={{
            current: page, pageSize: 20, total, showSizeChanger: false,
            showTotal: t => `共 ${t} 条`, onChange: setPage,
          }}
        />
      </div>

      <RequisitionEditorModal open={editorOpen} onClose={() => setEditorOpen(false)}
        onSaved={id => { if (id) navigate(`/purchase-requisitions/${id}`) }} />
    </div>
  )
}
