import { CLAIM_ITEM_OPTIONS } from '../../../../services/quality'

const ACTION_TEXT: Record<string, string> = {
  approve: '通过', reject: '驳回', recall: '撤回', auto_skip: '自动通过', revoked: '撤回审批',
}
const NO_RETURN_LINE = '无需退回，由恒剑直接处理 Not need to return, please HJ handle it directly'
const RETURN_LINE = '需退回，供应商承担运费 Please return, supplier will be charge of the transporting fee.'
const RETURN_LINES: Record<string, [string, string]> = {
  no_return: [`☑ ${NO_RETURN_LINE}`, `□ ${RETURN_LINE}`],
  return_supplier_fee: [`□ ${NO_RETURN_LINE}`, `☑ ${RETURN_LINE}`],
}

export type ClaimPaperOpinion = { label: string; text?: string; sign?: string; date?: string }

/** 从审批日志推导各级意见区（打印/详情共用）：轮内最后一个动作为准，签字人去重。 */
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

/** 纸质「供应商索赔通知单」版式 —— 新建预览（small）/ 详情只读 / 打印共用同一 markup。 */
export default function ClaimPaper({ claim, opinions = [], small = false }: {
  claim: any
  opinions?: ClaimPaperOpinion[]
  small?: boolean
}) {
  const items: string[] = claim?.claim_items || []
  const ck = (v: string) => (items.includes(v) ? '☑' : '□')
  const amount = claim?.claim_amount
  return (
    <div className={`clm-paper${small ? ' sm' : ''}`}>
      <div className="clm-row">
        <div className="clm-co">
          <b>宁波恒剑光电科技有限公司</b>
          <div className="en">IQC Department</div>
        </div>
        <div className="clm-ti">供应商索赔通知单<span className="en">Supplier Claim Confirmation</span></div>
        <div className="clm-no">
          NO. {claim?.claim_no || '-'}<br />
          Issue date: {claim?.claim_date || '-'}<br />
          1/1
        </div>
      </div>

      <div className="clm-sec">
        <span className="lbl">供应商 Supplier:</span>{' '}
        <b>{claim?.supplier_name || '-'}</b>
        {claim?.supplier_code ? `（${claim.supplier_code}）` : null}
      </div>

      <div className="clm-sec">
        <span className="lbl">索赔原因 Claim reason：</span>
        {claim?.claim_reason === 'field_customer_claim'
          ? <>■ 现场/客户投诉 Field/customer claim　□ 供货业绩 Supply performance</>
          : claim?.claim_reason === 'supply_performance'
            ? <>□ 现场/客户投诉 Field/customer claim　■ 供货业绩 Supply performance</>
            : <>□ 现场/客户投诉　□ 供货业绩</>}
        <div className="clm-clause">
          供应商索赔主要基于以下几个方面：交货和质量问题；制造过程中发现质量问题；导致我司客户索赔的质量问题。
        </div>
      </div>

      <div className="clm-sec">
        <span className="lbl">索赔细项 Details claimed：</span>
        <br />
        {CLAIM_ITEM_OPTIONS.slice(0, 3).map(o => <span key={o.value}>{ck(o.value)} {o.label}　</span>)}
        <br />
        {CLAIM_ITEM_OPTIONS.slice(3, 6).map(o => <span key={o.value}>{ck(o.value)} {o.label}　</span>)}
        <br />
        {CLAIM_ITEM_OPTIONS.slice(6).map(o => <span key={o.value}>{ck(o.value)} {o.label}　</span>)}
      </div>

      <div className="clm-sec">
        <span className="lbl">索赔方式：</span>{claim?.claim_method || '-'}
        <div className="clm-calc">索赔金额计算说明：{claim?.calc_explanation || '-'}</div>
        <div className="clm-amt">
          共计扣除费用 <b>{amount != null ? `¥${Number(amount).toLocaleString(undefined, { minimumFractionDigits: 2 })}` : '-'}</b> 元人民币。
        </div>
        <div className="clm-sign">
          品质部签字 Signature：{claim?.applicant_display || claim?.applicant || '-'}　{claim?.claim_date || ''}
        </div>
      </div>

      <div className="clm-sec">
        <span className="lbl">退回要求 About parts returned from field：</span>
        <br />
        {(RETURN_LINES[claim?.return_requirement] || ['□ 无需退回，由恒剑直接处理', '□ 需退回，供应商承担运费']).map((line, i) => (
          <span key={i}>{line}{i === 0 ? <br /> : null}</span>
        ))}
      </div>

      {opinions.length === 0
        ? <div className="clm-sec"><span className="who empty">—— 各级意见 / 签字区随审批进度填充 ——</span></div>
        : opinions.map((op, i) => (
          <div className="clm-sec" key={i}>
            <div><b>{op.label}：</b>{op.text}</div>
            <div className="who">签字 Signature：{op.sign || '-'}　{op.date}</div>
          </div>
        ))}

      <div className="clm-sec">备注：{claim?.remarks || '　'}</div>
    </div>
  )
}
