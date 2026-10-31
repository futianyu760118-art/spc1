import dayjs from 'dayjs'
import { materialApi } from '../../../../services/api'
import type { CreateAdapter, CreateBusinessEntry, FormSchema } from '../engine/types'

const schema: FormSchema = {
  bizType: 'purchase_requisition',
  title: '采购申请单',
  sections: [
    {
      title: '基本信息',
      fields: [
        { key: 'department', label: '部门（选填）', widget: 'text', placeholder: '如采购部' },
        { key: 'remark', label: '备注（选填）', widget: 'text', placeholder: '整单备注' },
      ],
    },
    {
      title: '申请明细',
      fields: [
        {
          key: 'lines', label: '申请明细', widget: 'detail_grid', required: true, span: 2,
          extra: '物料编码须存在于基础物料；保存时整单明细替换',
          columns: [
            { key: 'material_code', label: '物料编码', widget: 'text', required: true, width: 190, placeholder: '输入物料编码' },
            { key: 'req_qty', label: '数量', widget: 'number', required: true, positive: true, precision: 4, width: 130 },
            { key: 'need_date', label: '到货日期', widget: 'date', width: 150 },
            { key: 'remark', label: '备注', widget: 'text', width: 160, placeholder: '选填' },
          ],
        },
      ],
    },
  ],
  actions: { draft: true, submit: true },
}

function toPayload(values: Record<string, any>) {
  return {
    department: (values.department || '').trim() || null,
    remark: (values.remark || '').trim() || null,
    lines: (values.lines || []).map((line: any) => ({
      material_code: (line.material_code || '').trim(),
      req_qty: Number(line.req_qty),
      need_date: line.need_date ? dayjs(line.need_date).format('YYYY-MM-DD') : null,
      remark: (line.remark || '').trim() || null,
    })),
  }
}

const adapter: CreateAdapter = {
  initialValues: { lines: [{}] },
  async loadForEdit(id: number) {
    const res: any = await materialApi.getPurchaseRequisition(id)
    const record = res.data || {}
    const rows = (record.lines || []).map((line: any) => ({
      material_code: line.material_code || '',
      req_qty: line.req_qty ?? null,
      need_date: line.need_date ? dayjs(line.need_date) : null,
      remark: line.remark || '',
    }))
    return {
      department: record.department || '',
      remark: record.remark || '',
      lines: rows.length ? rows : [{}],
    }
  },
  async saveDraft(values, editId) {
    const payload = toPayload(values)
    if (editId) {
      await materialApi.updatePurchaseRequisition(editId, payload)
      return { id: editId }
    }
    const res: any = await materialApi.createPurchaseRequisition(payload)
    return { id: res.data?.id }
  },
  async submit(values, editId) {
    const payload = toPayload(values)
    let id = editId
    if (editId) {
      await materialApi.updatePurchaseRequisition(editId, payload)
    } else {
      const res: any = await materialApi.createPurchaseRequisition(payload)
      id = res.data?.id
    }
    await materialApi.submitPurchaseRequisition(id as number)
    return { id: id as number }
  },
}

export const purchaseRequisitionBusiness: CreateBusinessEntry = {
  bizType: 'purchase_requisition',
  name: '采购申请单',
  description: '手工建单（明细行），保存并提交后进入采购审批链',
  permission: ['materials.purchase_requisition', 'create'],
  schema,
  adapter,
}
