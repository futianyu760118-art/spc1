import type { CSSProperties } from 'react'
import { formatDateTime } from '../utils'
import { opinionsFromClaim } from './ClaimPaper'

export const REQUISITION_STATUS_MAP: Record<string, { text: string; cls: string }> = {
  draft: { text: '草稿', cls: 'sc-tag-wait' },
  approving: { text: '审批中', cls: 'sc-tag-kit' },
  approved: { text: '已批准', cls: 'sc-tag-done' },
  rejected: { text: '已驳回', cls: 'sc-tag-danger' },
  closed: { text: '已关闭', cls: 'sc-tag-plain' },
}

export const REQUISITION_SOURCE_MAP: Record<string, { text: string; cls: string }> = {
  manual: { text: '手工', cls: 'sc-tag-plain' },
  mrp: { text: 'MRP', cls: 'sc-tag-prod' },
  excel: { text: 'Excel', cls: 'sc-tag-kit' },
}

export const REQUISITION_LINE_STATUS_MAP: Record<string, { text: string; cls: string }> = {
  open: { text: '未转单', cls: 'sc-tag-wait' },
  partially_converted: { text: '部分转单', cls: 'sc-tag-amber' },
  closed: { text: '已转单', cls: 'sc-tag-done' },
}

export function fmtQty(v: any): string {
  if (v == null || v === '') return '-'
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}

export function fmtAmount(v: any): string {
  if (v == null || v === '') return '-'
  return `¥${Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export interface RequisitionLine {
  id: number
  line_no: number
  material_id?: number | null
  material_code: string
  material_name?: string | null
  spec_model?: string | null
  unit?: string | null
  req_qty: number
  need_date?: string | null
  supplier_id?: number | null
  supplier_code?: string | null
  supplier_name?: string | null
  unit_price?: number | null
  converted_qty: number
  converted_po_no?: string | null
  status: string
  remark?: string | null
}

export interface RequisitionLog {
  id: number
  approval_level?: number | null
  approver?: string | null
  action: string
  comment?: string | null
  operated_at?: string | null
  round?: number
}

export interface Requisition {
  id: number
  req_no: string
  status: string
  applicant?: string | null
  department?: string | null
  source: string
  run_id?: number | null
  remark?: string | null
  approval_status?: string | null
  approval_level?: number | null
  approval_snapshot?: Record<string, any>[]
  submitted_at?: string | null
  approved_by?: string | null
  approved_at?: string | null
  version: number
  created_at: string
  line_count: number
  total_amount: number
  total_qty?: number
  lines?: RequisitionLine[]
  approval_logs?: RequisitionLog[]
  approval_round?: number
}

const HEAD_CELLS: { label: string; align: 'left' | 'right' }[] = [
  { label: '行号', align: 'right' },
  { label: '物料编码', align: 'left' },
  { label: '物料名称 / 规格', align: 'left' },
  { label: '数量', align: 'right' },
  { label: '单位', align: 'left' },
  { label: '到货日期', align: 'left' },
  { label: '参考单价', align: 'right' },
  { label: '金额', align: 'right' },
  { label: '备注', align: 'left' },
]

const TH: CSSProperties = {
  borderBottom: '1px solid var(--clm-ink, #475569)',
  background: '#f8fafc',
  padding: '4px 6px',
  fontSize: 'inherit',
  fontWeight: 600,
  whiteSpace: 'nowrap',
}
const TD: CSSProperties = {
  borderBottom: '1px solid #e2e8f0',
  padding: '4px 6px',
  fontSize: 'inherit',
  verticalAlign: 'top',
}

/** 纸质「采购申请单 Purchase Requisition」版式 —— 详情屏幕与审批详情左栏共用。 */
export default function PurchaseRequisitionPaper({ req, small = false }: { req: any; small?: boolean }) {
  const lines: RequisitionLine[] = req?.lines || []
  const opinions = opinionsFromClaim(req)
  const status = REQUISITION_STATUS_MAP[req?.status]?.text || req?.status || '-'
  const totalQty = lines.length ? lines.reduce((s, l) => s + Number(l.req_qty || 0), 0) : Number(req?.total_qty || 0)
  const totalAmount = lines.length
    ? lines.reduce((s, l) => s + Number(l.req_qty || 0) * Number(l.unit_price || 0), 0)
    : Number(req?.total_amount || 0)

  return (
    <div className={`clm-paper${small ? ' sm' : ''}`}>
      <div className="clm-row">
        <div className="clm-co">
          <b>宁波恒剑光电科技有限公司</b>
          <div className="en">Procurement Department</div>
        </div>
        <div className="clm-ti">采购申请单<span className="en">Purchase Requisition</span></div>
        <div className="clm-no">
          NO. {req?.req_no || '-'}<br />
          日期 Date: {(req?.created_at || '').slice(0, 10) || '-'}<br />
          状态 Status: {status}
        </div>
      </div>

      <div className="clm-sec">
        <span className="lbl">申请人 Applicant：</span>{req?.applicant || '-'}　
        <span className="lbl">部门 Department：</span>{req?.department || '-'}　
        <span className="lbl">来源 Source：</span>{REQUISITION_SOURCE_MAP[req?.source]?.text || req?.source || '-'}　
        <span className="lbl">提交时间 Submitted：</span>{req?.submitted_at ? formatDateTime(req.submitted_at) : '-'}
      </div>

      <div className="clm-sec" style={{ padding: 0 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              {HEAD_CELLS.map(h => (
                <th key={h.label} style={{ ...TH, textAlign: h.align }}>{h.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {lines.length === 0 ? (
              <tr>
                <td colSpan={HEAD_CELLS.length} style={{ ...TD, textAlign: 'center', color: '#94a3b8' }}>无明细</td>
              </tr>
            ) : lines.map(l => (
              <tr key={l.id ?? l.line_no}>
                <td style={{ ...TD, textAlign: 'right' }} className="sc-mono">{l.line_no}</td>
                <td style={TD} className="sc-mono">{l.material_code}</td>
                <td style={TD}>
                  <div>{l.material_name || '-'}</div>
                  {l.spec_model ? <div style={{ color: '#64748b', fontSize: '0.92em' }}>{l.spec_model}</div> : null}
                </td>
                <td style={{ ...TD, textAlign: 'right' }} className="sc-mono">{fmtQty(l.req_qty)}</td>
                <td style={TD}>{l.unit || '-'}</td>
                <td style={TD}>{l.need_date || '-'}</td>
                <td style={{ ...TD, textAlign: 'right' }} className="sc-mono">
                  {l.unit_price == null ? '-' : Number(l.unit_price).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </td>
                <td style={{ ...TD, textAlign: 'right' }} className="sc-mono">
                  {l.unit_price == null ? '-' : fmtAmount(Number(l.req_qty || 0) * Number(l.unit_price))}
                </td>
                <td style={TD}>{l.remark || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="clm-sec">
        <div className="clm-amt">
          共计 <b>{lines.length}</b> 行，数量合计 <b>{fmtQty(totalQty)}</b>，预估金额合计 <b>{fmtAmount(totalAmount)}</b>。
        </div>
      </div>

      {opinions.length === 0
        ? <div className="clm-sec"><span className="who empty">—— 各级意见 / 签字区随审批进度填充 ——</span></div>
        : opinions.map((op, i) => (
          <div className="clm-sec" key={i}>
            <div><b>{op.label}：</b>{op.text}</div>
            <div className="who">签字 Signature：{op.sign || '-'}　{op.date}</div>
          </div>
        ))}

      <div className="clm-sec">备注：{req?.remark || '　'}</div>
    </div>
  )
}
