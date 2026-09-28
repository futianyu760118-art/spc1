import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button, Card, InputNumber, Modal, Spin, Table, message } from 'antd'
import { ArrowLeftOutlined, EditOutlined, ExportOutlined, SendOutlined, SwapOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { materialApi } from '../../../services/api'
import { useAuthStore } from '../../../store/auth'
import { useExport } from '../../../hooks/useExport'
import { formatDateTime } from '../../../utils'
import {
  REQUISITION_LINE_STATUS_MAP, REQUISITION_SOURCE_MAP, REQUISITION_STATUS_MAP,
  fmtAmount, fmtQty, type Requisition, type RequisitionLine,
} from '../../../components/PurchaseRequisitionPaper'
import { RequisitionEditorModal } from './index'

const ACTION_TAG: Record<string, { cls: string; text: string }> = {
  submit: { cls: 'sc-tag-kit', text: '提交' },
  approve: { cls: 'sc-tag-done', text: '通过' },
  reject: { cls: 'sc-tag-danger', text: '驳回' },
  recall: { cls: 'sc-tag-amber', text: '撤回' },
  auto_skip: { cls: 'sc-tag-done', text: '自动通过' },
  revoked: { cls: 'sc-tag-amber', text: '撤回审批' },
}

type ConvertRow = RequisitionLine & { qty: number }

export default function PurchaseRequisitionDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const hasPermission = useAuthStore((s) => s.hasPermission) as (resource: string, action: string) => boolean
  const canUpdate = hasPermission('materials.purchase_requisition', 'update')
  const canConvert = hasPermission('materials.purchase_requisition', 'convert')
  const { exporting, exportData } = useExport()

  const [r, setR] = useState<Requisition | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const [convertOpen, setConvertOpen] = useState(false)
  const [convertLines, setConvertLines] = useState<ConvertRow[]>([])
  const [converting, setConverting] = useState(false)

  const load = useCallback(async () => {
    if (!id) return
    try {
      const res: any = await materialApi.getPurchaseRequisition(parseInt(id))
      setR(res.data || null)
    } catch { /* 全局拦截器已提示 */ }
  }, [id])
  useEffect(() => { load() }, [load])

  if (!r) return <div className="sc-page"><Card styles={{ body: { padding: 60 } }}><Spin /></Card></div>

  const status = r.status
  const statusTag = REQUISITION_STATUS_MAP[status] || { text: status, cls: 'sc-tag-plain' }
  const canEdit = canUpdate && (status === 'draft' || status === 'rejected')
  const lines = r.lines || []
  const logs = r.approval_logs || []
  const rounds = [...new Set(logs.map(l => l.round ?? 1))]
  const nodeLabel = (level?: number | null) =>
    (r.approval_snapshot || []).find((n: any) => n.seq === level)?.label || (level ? `L${level}` : '')
  const currentNode: any = (r.approval_snapshot || []).find((n: any) => n.seq === r.approval_level)
  const remaining = (l: RequisitionLine) => Math.max(0, Number(l.req_qty || 0) - Number(l.converted_qty || 0))

  const doExport = () =>
    exportData(`/api/v1/materials/purchase-requisitions/${r.id}/export`, { format: 'csv' }, `${r.req_no}-采购申请单.csv`)

  const doSubmit = () => Modal.confirm({
    title: '提交审批',
    okText: '确认提交',
    content: (
      <div>
        确认提交 <b className="sc-mono">{r.req_no}</b>？
        <div className="f-note" style={{ marginTop: 10 }}>
          提交后按当前审批链冻结快照；若未配置采购申请单审批链将无法提交，需先在「审批配置」中配置。
        </div>
      </div>
    ),
    onOk: async () => {
      try {
        const res: any = await materialApi.submitPurchaseRequisition(r.id)
        message.success(res.message || '提交成功')
        load()
      } catch (e: any) {
        message.error(e?.response?.data?.detail || e?.message || '提交失败')
      }
    },
  })

  const openConvert = () => {
    setConvertLines(
      lines.filter(l => l.status !== 'closed' && remaining(l) > 0).map(l => ({ ...l, qty: remaining(l) })),
    )
    setConvertOpen(true)
  }

  const doConvert = async () => {
    const items = convertLines.filter(l => Number(l.qty) > 0).map(l => ({ line_id: l.id, qty: Number(l.qty) }))
    if (items.length === 0) { message.warning('请至少填写一行转单数量'); return }
    for (const l of convertLines) {
      if (Number(l.qty) > remaining(l)) { message.warning(`第 ${l.line_no} 行本次转单数量超过剩余可转量`); return }
    }
    setConverting(true)
    try {
      const res: any = await materialApi.convertPurchaseRequisitionToPo(r.id, items)
      message.success(`已生成 ${res.data?.created ?? items.length} 条采购订单${res.data?.closed ? '，申请单已全部转单关闭' : ''}`)
      setConvertOpen(false)
      load()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '转采购订单失败')
    } finally { setConverting(false) }
  }

  const lineColumns: ColumnsType<RequisitionLine> = [
    { title: '行号', dataIndex: 'line_no', width: 56, align: 'right', render: (v: number) => <span className="sc-mono">{v}</span> },
    { title: '物料编码', dataIndex: 'material_code', width: 140, render: (v: string) => <span className="sc-mono">{v}</span> },
    {
      title: '物料名称 / 规格', ellipsis: true,
      render: (_: any, l) => (
        <div style={{ minWidth: 0 }}>
          <div>{l.material_name || '-'}</div>
          {l.spec_model ? <div className="sc-note">{l.spec_model}</div> : null}
        </div>
      ),
    },
    { title: '单位', dataIndex: 'unit', width: 60, render: (v: string) => v || '-' },
    { title: '申请数量', dataIndex: 'req_qty', width: 96, align: 'right', render: (v: number) => <span className="sc-mono">{fmtQty(v)}</span> },
    { title: '到货日期', dataIndex: 'need_date', width: 104, render: (v: string) => v || '-' },
    {
      title: '建议供应商', dataIndex: 'supplier_name', width: 170, ellipsis: true,
      render: (v: string, l) => (
        <div style={{ minWidth: 0 }}>
          <div>{v || '-'}</div>
          {l.supplier_code ? <div className="sc-note sc-mono">{l.supplier_code}</div> : null}
        </div>
      ),
    },
    {
      title: '参考单价', dataIndex: 'unit_price', width: 90, align: 'right',
      render: (v: number | null) => v == null ? '-' : (
        <span className="sc-mono">{Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
      ),
    },
    {
      title: '金额', width: 100, align: 'right',
      render: (_: any, l) => <span className="sc-mono">{l.unit_price == null ? '-' : fmtAmount(Number(l.req_qty || 0) * Number(l.unit_price))}</span>,
    },
    { title: '已转数量', dataIndex: 'converted_qty', width: 90, align: 'right', render: (v: number) => <span className="sc-mono">{fmtQty(v)}</span> },
    { title: '转单号', dataIndex: 'converted_po_no', width: 150, render: (v: string) => v ? <span className="sc-mono">{v}</span> : '-' },
    {
      title: '行状态', dataIndex: 'status', width: 92,
      render: (v: string) => {
        const s = REQUISITION_LINE_STATUS_MAP[v] || { text: v, cls: 'sc-tag-plain' }
        return <span className={`sc-tag ${s.cls}`}>{s.text}</span>
      },
    },
    { title: '备注', dataIndex: 'remark', width: 140, ellipsis: true, render: (v: string) => v || '-' },
  ]

  const convertColumns: ColumnsType<ConvertRow> = [
    { title: '行号', dataIndex: 'line_no', width: 56, align: 'right' },
    { title: '物料编码', dataIndex: 'material_code', width: 140, render: (v: string) => <span className="sc-mono">{v}</span> },
    { title: '物料名称', dataIndex: 'material_name', ellipsis: true },
    { title: '申请数量', dataIndex: 'req_qty', width: 90, align: 'right', render: (v: number) => <span className="sc-mono">{fmtQty(v)}</span> },
    { title: '已转数量', dataIndex: 'converted_qty', width: 90, align: 'right', render: (v: number) => <span className="sc-mono">{fmtQty(v)}</span> },
    { title: '剩余可转', width: 90, align: 'right', render: (_: any, l) => <span className="sc-mono">{fmtQty(remaining(l))}</span> },
    {
      title: '本次转单数量', width: 140, align: 'right',
      render: (_: any, l) => (
        <InputNumber min={0} max={remaining(l)} precision={4} value={l.qty} style={{ width: '100%' }}
          onChange={v => setConvertLines(prev => prev.map(x => (x.id === l.id ? { ...x, qty: Number(v || 0) } : x)))} />
      ),
    },
  ]

  return (
    <div className="sc-page">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/purchase-requisitions')}>返回台账</Button>
        <span className="sc-mono" style={{ fontSize: 18, fontWeight: 600 }}>{r.req_no}</span>
        <span className={`sc-tag ${statusTag.cls}`}><span className="dot" />{statusTag.text}</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Button icon={<ExportOutlined />} loading={exporting} onClick={doExport}>导出</Button>
          {canEdit && <Button icon={<EditOutlined />} onClick={() => setEditorOpen(true)}>编辑</Button>}
          {canEdit && (
            <Button type="primary" icon={<SendOutlined />} onClick={doSubmit}>
              {status === 'draft' ? '提交审批' : '重新提交'}
            </Button>
          )}
          {status === 'approved' && canConvert && (
            <Button type="primary" icon={<SwapOutlined />} onClick={openConvert}>转采购订单</Button>
          )}
        </div>
      </div>

      <div className="clm-detail-grid">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
          <Card title="申请明细" size="small"
            extra={<span className="sc-note">共 {lines.length} 行 · 预估金额 {fmtAmount(r.total_amount)}</span>}
            styles={{ body: { padding: '0 0 4px' } }}>
            <Table<RequisitionLine>
              rowKey="id" dataSource={lines} columns={lineColumns} pagination={false} size="small"
              scroll={{ x: 1360 }}
              summary={() => (
                <Table.Summary.Row className="sc-note">
                  <Table.Summary.Cell index={0} colSpan={4}>本单 {lines.length} 行</Table.Summary.Cell>
                  <Table.Summary.Cell index={4} align="right">
                    <b className="sc-mono" style={{ color: '#0f172a' }}>{fmtQty(r.total_qty ?? 0)}</b>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={5} colSpan={3} />
                  <Table.Summary.Cell index={8} align="right">
                    <b className="sc-mono" style={{ color: '#0f172a' }}>{fmtAmount(r.total_amount)}</b>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={9} colSpan={4} />
                </Table.Summary.Row>
              )}
              locale={{ emptyText: '暂无明细' }}
            />
          </Card>

          <Card title="审批意见" size="small">
            {logs.length === 0 ? (
              <div className="sc-note">暂无审批记录——提交后逐条留档，重新提交按轮次分组。</div>
            ) : rounds.map(rn => (
              <div key={rn} style={{ marginBottom: rounds[rounds.length - 1] === rn ? 0 : 14 }}>
                <div className="sc-note" style={{ fontWeight: 600, marginBottom: 8 }}>
                  第 {rn} 轮{rn < rounds[rounds.length - 1] ? '（历史存档）' : ''}
                </div>
                <div className="ac-timeline">
                  {logs.filter(l => (l.round ?? 1) === rn).map((l, i) => {
                    const tag = ACTION_TAG[l.action] || { cls: 'sc-tag-wait', text: l.action }
                    return (
                      <div key={i} className="ac-tl-item done">
                        <div className="t sc-mono">{formatDateTime(l.operated_at)}</div>
                        <div className="what">
                          {l.approver || '-'} <span className={`sc-tag ${tag.cls}`}>{tag.text}</span>
                          {l.approval_level ? ` · ${nodeLabel(l.approval_level)}` : ''}
                        </div>
                        {l.comment ? <div className="who">{l.comment}</div> : null}
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </Card>
        </div>

        <div className="clm-sticky">
          <Card title="单据信息" size="small" styles={{ body: { padding: '12px 16px' } }}>
            <dl className="clm-kv">
              <dt>申请人</dt><dd>{r.applicant || '-'}</dd>
              <dt>部门</dt><dd>{r.department || '-'}</dd>
              <dt>来源</dt><dd>{REQUISITION_SOURCE_MAP[r.source]?.text || r.source || '-'}</dd>
              <dt>创建时间</dt><dd>{formatDateTime(r.created_at)}</dd>
              {r.submitted_at ? <><dt>提交时间</dt><dd>{formatDateTime(r.submitted_at)}</dd></> : null}
              {r.approved_at ? <><dt>通过时间</dt><dd>{formatDateTime(r.approved_at)}</dd></> : null}
              {r.approved_by ? <><dt>审批人</dt><dd>{r.approved_by}</dd></> : null}
              {status === 'approving' && currentNode ? <><dt>当前节点</dt><dd>{currentNode.label || '-'}</dd></> : null}
              <dt>备注</dt><dd>{r.remark || '-'}</dd>
            </dl>
          </Card>
          <Card size="small" styles={{ body: { padding: '12px 16px' } }}>
            <div className="sc-note" style={{ lineHeight: 1.9 }}>
              审批通过后可在本页「转采购订单」按行转单（生成 SPC 采购订单，PO 号 MRP-申请单号-行号）；
              剩余数量可分批转单，全部转完后申请单自动关闭。
            </div>
          </Card>
        </div>
      </div>

      <RequisitionEditorModal open={editorOpen} editId={r.id} onClose={() => setEditorOpen(false)} onSaved={() => load()} />

      <Modal title="转采购订单" open={convertOpen} width={760} okText="确认转单" confirmLoading={converting}
        onOk={doConvert} onCancel={() => setConvertOpen(false)} maskClosable={false}>
        <div className="f-note" style={{ marginBottom: 10 }}>
          按行填写本次转单数量（默认剩余可转量）；数量超过剩余量或行已关闭时后端将拒绝。
        </div>
        <Table<ConvertRow>
          rowKey="id" dataSource={convertLines} columns={convertColumns} pagination={false} size="small"
          scroll={{ x: 720 }} locale={{ emptyText: '没有可转单的明细行' }}
        />
      </Modal>
    </div>
  )
}
