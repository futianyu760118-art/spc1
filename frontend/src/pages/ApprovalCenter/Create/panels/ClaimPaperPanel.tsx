import { Form } from 'antd'
import type { FormInstance } from 'antd'
import ClaimPaper from '../../../../components/ClaimPaper'
import { registerPanel } from '../engine/registry'

function ClaimPaperPanel({ form }: { form: FormInstance }) {
  const toPreview = (values: Record<string, any>) => ({
    claim_no: values.claim_no,
    supplier_name: values.supplier_name,
    supplier_code: values.supplier_code,
    claim_reason: values.claim_reason,
    claim_items: values.claim_items || [],
    claim_amount: values.claim_amount,
    claim_date: values.claim_date?.format?.('YYYY-MM-DD'),
    claim_method: values.claim_method,
    calc_explanation: values.calc_explanation,
    return_requirement: values.return_requirement,
    remarks: values.remarks,
  })
  return (
    <Form.Item noStyle shouldUpdate>
      {() => <ClaimPaper small claim={toPreview(form.getFieldsValue(true))} />}
    </Form.Item>
  )
}

registerPanel('claim_paper_preview', ClaimPaperPanel)
export default ClaimPaperPanel
