import dayjs from 'dayjs'
import {
  CLAIM_ITEM_OPTIONS, CLAIM_REASON_OPTIONS, CLAIM_RETURN_OPTIONS, qualityApi,
} from '../../../../services/quality'
import type { CreateAdapter, CreateBusinessEntry, FormSchema } from '../engine/types'
import '../panels/ClaimPaperPanel'

const schema: FormSchema = {
  bizType: 'supplier_claim',
  title: '供应商索赔单',
  sections: [
    {
      title: '基本信息',
      fields: [
        { key: 'supplier_code', label: '供应商编码', widget: 'text', hidden: true },
        { key: 'supplier_name', label: '供应商 Supplier', widget: 'remote_select', remote: 'supplier',
          required: true, placeholder: '输入关键词搜索供应商', derive: { supplier_code: 'supplier_code' } },
        { key: 'claim_date', label: '开单日期 Issue date', widget: 'date', required: true },
        { key: 'claim_reason', label: '索赔原因 Claim reason', widget: 'radio_cards',
          options: CLAIM_REASON_OPTIONS, required: true, span: 2 },
        { key: 'return_requirement', label: '退回要求 About parts returned from field', widget: 'radio_cards',
          options: CLAIM_RETURN_OPTIONS, required: true, span: 2 },
      ],
    },
    {
      title: '索赔细项与金额',
      fields: [
        { key: 'claim_items', label: '索赔细项 Details claimed（至少一项）', widget: 'checkbox_cards',
          options: CLAIM_ITEM_OPTIONS, required: true, span: 2 },
        { key: 'claim_amount', label: '索赔金额（元）', widget: 'number', required: true, min: 0, precision: 2 },
        { key: 'claim_method', label: '索赔方式', widget: 'text', placeholder: '如：本公司财务部直接扣款' },
      ],
    },
    {
      title: '计算说明与凭证',
      fields: [
        { key: 'calc_explanation', label: '索赔金额计算说明（将原样打印在纸质单上）', widget: 'textarea', span: 2, rows: 4 },
        { key: 'remarks', label: '备注', widget: 'textarea', span: 2, rows: 2 },
        { key: 'attachments', label: '附件（检验报告 / 照片等）', widget: 'upload',
          uploadNamespace: 'supplier-claim', span: 2 },
      ],
    },
  ],
  aside: { component: 'claim_paper_preview', title: '纸质单预览' },
  actions: { draft: true, submit: true },
}

function toPayload(values: Record<string, any>) {
  return {
    ...values,
    claim_date: values.claim_date ? dayjs(values.claim_date).format('YYYY-MM-DD') : undefined,
    attachments: (values.attachments || []).map((f: any) => f.response || f),
  }
}

const adapter: CreateAdapter = {
  initialValues: {
    claim_date: dayjs(),
    claim_reason: 'field_customer_claim',
    return_requirement: 'no_return',
    claim_items: [],
  },
  async loadForEdit(id: number) {
    const res: any = await qualityApi.get(id)
    const record = res.data || {}
    return {
      ...record,
      claim_date: record.claim_date ? dayjs(record.claim_date) : undefined,
      attachments: (record.attachments || []).map((a: any, index: number) => ({
        uid: a.id ? String(a.id) : String(index),
        name: a.name || a.file_name || '附件',
        status: 'done',
        url: a.url,
        response: a,
      })),
    }
  },
  async saveDraft(values, editId) {
    const payload = toPayload(values)
    if (editId) {
      await qualityApi.update(editId, { ...payload, submit: false })
      return { id: editId }
    }
    const res: any = await qualityApi.create({ ...payload, submit: false })
    return { id: res.data?.id }
  },
  async submit(values, editId) {
    const payload = toPayload(values)
    if (editId) {
      await qualityApi.update(editId, { ...payload, submit: false })
      await qualityApi.submit(editId)
      return { id: editId }
    }
    const res: any = await qualityApi.create({ ...payload, submit: true })
    return { id: res.data?.id }
  },
}

export const supplierClaimBusiness: CreateBusinessEntry = {
  bizType: 'supplier_claim',
  name: '供应商索赔单',
  description: '按纸质版式在线填单，提交后进入索赔审批链',
  permission: ['quality.supplier_claim', 'create'],
  schema,
  adapter,
}
