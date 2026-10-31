import { CLAIM_ITEM_OPTIONS } from '../services/quality'
import { useClaimTemplate } from '../hooks/useClaimTemplate'

const ACTION_TEXT: Record<string, string> = {
  approve: '通过', reject: '驳回', recall: '撤回', auto_skip: '自动通过', revoked: '撤回审批',
}
const NO_RETURN_LINE = '无需退回，由恒剑直接处理 Not need to return, please HJ handle it directly'
const RETURN_LINE = '需退回，供应商承担运费 Please return, supplier will be charge of the transporting fee.'
const RETURN_OPTIONS = [
  { value: 'no_return', text: NO_RETURN_LINE },
  { value: 'return_supplier_fee', text: RETURN_LINE },
]

const CLAIM_OPINION_ROWS = [
  { slot: 'claim_dept', label: '索赔部门意见', aliases: ['索赔部门意见'], en: '', role: 'purchase_manager' },
  { slot: 'upper_dept', label: '上级部门意见(必要时)', aliases: ['上级部门意见', '上级部门意见(必要时)'], en: 'Comments of upper level manager, if necessary', role: 'manager' },
  { slot: 'general_manager', label: '总经理意见(必要时)', aliases: ['总经理意见', '总经理意见(必要时)'], en: 'Comments of president, if necessary', role: 'general_manager' },
  { slot: 'finance', label: '财务结算信息', aliases: ['财务结算', '财务结算信息'], en: 'Financial information', role: 'finance' },
]

export type ClaimPaperOpinion = { label: string; en?: string; text?: string; sign?: string; date?: string }

/** 采购申请单等其它单据继续使用：按审批日志推导意见区。 */
export function opinionsFromClaim(claim: any): ClaimPaperOpinion[] {
  const logs = (claim?.approval_logs || []).filter((l: any) => l.action !== 'submit')
  const levels = [...new Set(logs.map((l: any) => l.approval_level))]
  const snap = claim?.approval_snapshot || []
  return levels.map(lv => {
    const lvLogs = logs.filter((l: any) => l.approval_level === lv)
    const last = lvLogs[lvLogs.length - 1]
    return {
      label: snap.find((n: any) => n.seq === lv)?.label || `第 ${lv} 级意见`,
      text: last?.comment || lvLogs.map((l: any) => `${l.approver} ${ACTION_TEXT[l.action] || l.action}`).join('；'),
      sign: [...new Set(lvLogs.map((l: any) => l.approver))].join('、'),
      date: last?.operated_at ? String(last.operated_at).slice(0, 10) : '',
    }
  })
}

/** 索赔单固定四栏：先按标签别名、再按角色匹配快照；金额条件会重排 seq，不能按 seq 硬映射。 */
export function claimOpinionRows(claim: any): ClaimPaperOpinion[] {
  const currentRound = claim?.approval_round
  const logs = (claim?.approval_logs || []).filter((l: any) =>
    l.action !== 'submit' && (currentRound == null || l.round === currentRound))
  const snap = claim?.approval_snapshot || []
  const matched = new Set<any>()
  return CLAIM_OPINION_ROWS.map(row => {
    const findNode = (predicate: (node: any) => boolean) =>
      snap.find((n: any) => !matched.has(n.seq) && predicate(n))
    const node = findNode((n: any) => n.paper_slot === row.slot)
      || findNode((n: any) => (row.aliases as string[]).includes(n.label))
      || findNode((n: any) => n.role === row.role)
      || findNode((n: any) => logs.some((l: any) => l.approval_level === n.seq))
    if (node) matched.add(node.seq)
    const nodeLogs = node ? logs.filter((l: any) => l.approval_level === node.seq) : []
    const last = nodeLogs[nodeLogs.length - 1]
    return {
      label: row.label,
      en: row.en,
      text: last?.comment
        || nodeLogs.map((l: any) => `${l.approver_display || l.approver} ${ACTION_TEXT[l.action] || l.action}`).join('；'),
      sign: [...new Set(nodeLogs.map((l: any) => l.approver_display || l.approver))].join('、'),
      date: last?.operated_at ? String(last.operated_at).slice(0, 10) : '',
    }
  })
}

function formatAmount(value: any): string {
  if (value == null || value === '') return '-'
  const n = Number(value)
  if (Number.isNaN(n)) return '-'
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}

function ClaimPaperHeader({ claim }: { claim: any }) {
  return (
    <div className="clm-row">
      <div className="clm-co">
        <b>宁波恒剑光电科技有限公司</b>
        <div className="en">IQC Department</div>
      </div>
      <div className="clm-ti">供应商索赔通知单<span className="en">Supplier Claim Confirmation</span></div>
      <div className="clm-no">
        <div>
          <div>NO. {claim?.claim_no || '-'}</div>
          <div>Issue date: {claim?.claim_date || '-'}</div>
        </div>
        <div className="page">1/1</div>
      </div>
    </div>
  )
}

function ClaimPaperReason({ claim }: { claim: any }) {
  const mark = (value: string) => (claim?.claim_reason === value ? '■' : '□')
  return (
    <div className="clm-sec">
      <span className="lbl">索赔原因 Claim reason：</span>
      {mark('field_customer_claim')} 现场/客户投诉 Field/customer claim　
      {mark('supply_performance')} 供货业绩 Supply performance
      <div className="clm-clause">
        供应商索赔主要基于以下几个方面：<br />
        - 供应商交货和质量问题；<br />
        - 制造过程中发现供应商质量问题；<br />
        - 导致我司客户索赔的质量问题。
      </div>
    </div>
  )
}

function ClaimCheck({ checked }: { checked: boolean }) {
  return <span className={`clm-check${checked ? ' on' : ''}`} aria-hidden="true" />
}

function ClaimPaperItems({ claim }: { claim: any }) {
  const items: string[] = claim?.claim_items || []
  return (
    <div className="clm-sec">
      <span className="lbl">索赔细项 Details claimed：</span>
      <br />
      <div className="clm-item-grid">
        {CLAIM_ITEM_OPTIONS.map(option => (
          <span key={option.value}><ClaimCheck checked={items.includes(option.value)} /> {option.label}</span>
        ))}
      </div>
    </div>
  )
}

function ClaimPaperCalculation({ claim, clauses, defaultMethod }: {
  claim: any
  clauses: string[]
  defaultMethod: string
}) {
  return (
    <div className="clm-sec clm-calc-sec">
      <span className="lbl">索赔方式及费用计算说明 Explanation of claim method &amp; expense calculation：</span>
      <div className="clm-calc">索赔方式：{claim?.claim_method || defaultMethod || '-'}</div>
      <div className="clm-calc">索赔计算方式说明（参考质量协议）：</div>
      <div className="clm-clauses">
        {clauses.map((clause, index) => <div key={index}>{index + 1}、{clause}</div>)}
      </div>
      <div className="clm-calc">索赔金额计算：</div>
      <div className="clm-calc" style={{ whiteSpace: 'pre-line' }}>{claim?.calc_explanation || '-'}</div>
      <div className="clm-calc-foot">
        <div className="clm-amt">
          根据上述情况，共计扣除贵司费用 <b>{formatAmount(claim?.claim_amount)}</b> 元人民币，将直接从贵司货款中扣除。
        </div>
        <div className="clm-sign">
          签字 Signature：{claim?.applicant_display || claim?.applicant || '-'}　{claim?.claim_date || ''}
        </div>
      </div>
    </div>
  )
}

function OpinionBox({ opinion }: { opinion: ClaimPaperOpinion }) {
  return (
    <div className="clm-opinion">
      <div className="clm-opinion-lbl">
        <b>{opinion.label}</b>
        {opinion.en ? <span className="en">{opinion.en}</span> : null}
      </div>
      <div className={`clm-opinion-text${opinion.text ? '' : ' empty'}`}>{opinion.text || '　'}</div>
      <div className="who">签字 Signature：{opinion.sign || '　'}　{opinion.date || ''}</div>
    </div>
  )
}

/** 纸质「供应商索赔通知单」版式 —— 新建预览（small）/ 详情只读 / 打印共用同一 markup。 */
export default function ClaimPaper({ claim, small = false }: {
  claim: any
  small?: boolean
}) {
  const snapshot = claim?.clause_snapshot
  const hasSnapshot = Array.isArray(snapshot) && snapshot.length > 0
  const template = useClaimTemplate(!hasSnapshot)
  const clauses: string[] = hasSnapshot ? snapshot : template.clauses
  const rows = claimOpinionRows(claim)

  return (
    <div className={`clm-paper clm-claim${small ? ' sm' : ''}`}>
      <ClaimPaperHeader claim={claim} />

      <div className="clm-sec">
        <span className="lbl">供应商 Supplier:</span>{' '}
        <b>{claim?.supplier_name || '-'}</b>
        {claim?.supplier_code ? `（${claim.supplier_code}）` : null}
      </div>

      <ClaimPaperReason claim={claim} />
      <ClaimPaperItems claim={claim} />
      <ClaimPaperCalculation claim={claim} clauses={clauses} defaultMethod={template.claim_method_default} />

      <div className="clm-sec">
        <span className="lbl">退回要求 About parts returned from field：</span>
        <br />
        {RETURN_OPTIONS.map((option, index) => (
          <span key={option.value}>
            <ClaimCheck checked={claim?.return_requirement === option.value} /> {option.text}
            {index === 0 ? <br /> : null}
          </span>
        ))}
      </div>

      <div className="clm-opinion-row"><OpinionBox opinion={rows[0]} /></div>
      <div className="clm-opinion-row two">
        <OpinionBox opinion={rows[1]} />
        <OpinionBox opinion={rows[2]} />
      </div>
      <div className="clm-opinion-row"><OpinionBox opinion={rows[3]} /></div>

      <div className="clm-sec">备注：{claim?.remarks || '　'}</div>
    </div>
  )
}
