import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Button, Card, Checkbox, DatePicker, Form, Input, InputNumber, Popconfirm, Radio, Select, Upload, message } from 'antd'
import { ArrowLeftOutlined, InboxOutlined, SaveOutlined, SendOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { qualityApi, CLAIM_REASON_OPTIONS, CLAIM_ITEM_OPTIONS, CLAIM_RETURN_OPTIONS } from '../../../services/quality'
import { fileApi } from '../../../services/api'
import ClaimPaper from './components/ClaimPaper'

type SupplierOption = { id: number; supplier_code: string; supplier_name: string }

export default function SupplierClaimNew() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const editId = searchParams.get('edit')
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const [supplierOpts, setSupplierOpts] = useState<SupplierOption[]>([])
  const [supplierCode, setSupplierCode] = useState('')
  const [attachments, setAttachments] = useState<any[]>([])
  const [editNo, setEditNo] = useState('')

  // 表单值 → 右侧纸质单实时预览 / 卡片选中态（watch 必须无条件置于组件顶层）
  const reason = Form.useWatch('claim_reason', form)
  const returnReq = Form.useWatch('return_requirement', form)
  const itemVals: string[] = Form.useWatch('claim_items', form) || []
  const watched = {
    supplier_name: Form.useWatch('supplier_name', form),
    claim_amount: Form.useWatch('claim_amount', form),
    claim_date: Form.useWatch('claim_date', form) as any,
    claim_method: Form.useWatch('claim_method', form),
    calc_explanation: Form.useWatch('calc_explanation', form),
    remarks: Form.useWatch('remarks', form),
  }
  const preview = {
    claim_no: editNo || undefined,
    supplier_name: watched.supplier_name,
    supplier_code: supplierCode,
    claim_reason: reason,
    claim_items: itemVals,
    claim_amount: watched.claim_amount,
    claim_date: watched.claim_date?.format?.('YYYY-MM-DD'),
    claim_method: watched.claim_method,
    calc_explanation: watched.calc_explanation,
    return_requirement: returnReq,
    remarks: watched.remarks,
  }

  useEffect(() => {
    if (!editId) return
    ;(async () => {
      try {
        const res: any = await qualityApi.get(parseInt(editId))
        const r = res.data
        form.setFieldsValue({ ...r, claim_date: r.claim_date ? dayjs(r.claim_date) : undefined })
        setEditNo(r.claim_no || '')
        setSupplierCode(r.supplier_code || '')
        setAttachments(r.attachments || [])
      } catch { /* 全局拦截器已提示 */ }
    })()
  }, [editId]) // eslint-disable-line react-hooks/exhaustive-deps

  const searchSuppliers = async (keyword: string) => {
    if (!keyword) return
    try {
      const res: any = await qualityApi.searchSuppliers(keyword)
      setSupplierOpts(res.data?.items || [])
    } catch { /* 全局拦截器已提示 */ }
  }

  const toggleItem = (value: string, checked: boolean) => {
    form.setFieldValue('claim_items', checked ? [...itemVals, value] : itemVals.filter(v => v !== value))
  }

  const save = async (submit: boolean) => {
    const values = await form.validateFields()
    const payload = {
      ...values,
      supplier_code: supplierCode,
      claim_date: values.claim_date ? values.claim_date.format('YYYY-MM-DD') : undefined,
      attachments: attachments.map(f => f.response || f),
      submit,
    }
    setSaving(true)
    try {
      if (editId) {
        await qualityApi.update(parseInt(editId), { ...payload, submit: false })
        if (submit) await qualityApi.submit(parseInt(editId))
      } else {
        await qualityApi.create(payload)
      }
      message.success(submit ? '已提交审批' : '保存成功')
      navigate('/quality/supplier-claims')
    } catch { /* 全局拦截器已提示 */ } finally { setSaving(false) }
  }

  const radioCard = (name: 'claim_reason' | 'return_requirement', current: any, value: string, zh: string, en: string) => (
    <Radio className={`clm-rcard${current === value ? ' on' : ''}`} value={value}
      checked={current === value}
      onChange={() => form.setFieldValue(name, value)}>
      <span className="rc-txt">
        <span className="tt">{current === value ? '■' : '□'} {zh}</span>
        {en ? <span className="en">{en}</span> : null}
      </span>
    </Radio>
  )

  return (
    <div className="sc-page">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/quality/supplier-claims')}>返回台账</Button>
        <div>
          <div style={{ fontSize: 18, fontWeight: 600 }}>{editNo ? `编辑索赔单 ${editNo}` : '新建供应商索赔单'}</div>
          <div className="sc-note" style={{ marginTop: 2 }}>按纸质「供应商索赔通知单 Supplier Claim Confirmation」线上化 · 提交后进入审批链</div>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <Button icon={<SaveOutlined />} loading={saving} onClick={() => save(false)}>仅存草稿</Button>
          <Popconfirm title="提交审批" description="提交后将冻结当前审批链快照（按金额条件过滤节点），确认提交？"
            onConfirm={() => save(true)} okText="确认提交" cancelText="再检查一下">
            <Button type="primary" icon={<SendOutlined />} loading={saving}>保存并提交审批</Button>
          </Popconfirm>
        </div>
      </div>

      <Form form={form} layout="vertical"
        initialValues={{ claim_date: dayjs(), claim_reason: 'field_customer_claim', return_requirement: 'no_return', claim_items: [] }}>
        {/* 卡片选中态由组件渲染维护，隐藏 Item 仅承载表单值 */}
        <Form.Item name="claim_reason" hidden><Input /></Form.Item>
        <Form.Item name="return_requirement" hidden><Input /></Form.Item>
        <Form.Item name="claim_items" hidden><Input /></Form.Item>

        <div className="clm-form-grid">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
            <Card title="基本信息" styles={{ body: { paddingTop: 8 } }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
                <Form.Item name="supplier_name" label="供应商 Supplier" rules={[{ required: true, message: '请选择供应商' }]}>
                  <Select showSearch filterOption={false} placeholder="输入关键词搜索供应商"
                    onSearch={searchSuppliers}
                    onSelect={(_v: any, opt: any) => setSupplierCode(opt.supplier_code || '')}
                    options={supplierOpts.map(s => ({
                      value: s.supplier_name, label: `${s.supplier_name}（${s.supplier_code}）`, supplier_code: s.supplier_code,
                    }))} />
                </Form.Item>
                <Form.Item name="claim_date" label="开单日期 Issue date" rules={[{ required: true }]}>
                  <DatePicker style={{ width: '100%' }} />
                </Form.Item>
              </div>
              <Form.Item label="索赔原因 Claim reason" required style={{ marginBottom: 12 }}>
                <div className="clm-rcards">
                  {CLAIM_REASON_OPTIONS.map(o => radioCard('claim_reason', reason, o.value, o.label.split(' ')[0], o.label.split(' ').slice(1).join(' ')))}
                </div>
              </Form.Item>
              <Form.Item label="退回要求 About parts returned from field" required style={{ marginBottom: 0 }}>
                <div className="clm-rcards">
                  {CLAIM_RETURN_OPTIONS.map(o => radioCard('return_requirement', returnReq, o.value, o.label, ''))}
                </div>
              </Form.Item>
            </Card>

            <Card title="索赔细项与金额" styles={{ body: { paddingTop: 12 } }}>
              <Form.Item label="索赔细项 Details claimed（至少一项，打印时按纸质单八项排版）" required>
                <div className="clm-ccards">
                  {CLAIM_ITEM_OPTIONS.map(o => (
                    <label key={o.value} className={`clm-ccard${itemVals.includes(o.value) ? ' on' : ''}`}>
                      <Checkbox checked={itemVals.includes(o.value)} onChange={e => toggleItem(o.value, e.target.checked)} />
                      <span>{o.label.split(' ')[0]}</span>
                    </label>
                  ))}
                </div>
              </Form.Item>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
                <Form.Item name="claim_amount" label="索赔金额（元）" rules={[{ required: true, message: '请填写索赔金额' }]}>
                  <InputNumber min={0} precision={2} style={{ width: '100%' }} prefix="¥" />
                </Form.Item>
                <Form.Item name="claim_method" label="索赔方式">
                  <Input placeholder="如：本公司财务部直接扣款" />
                </Form.Item>
              </div>
            </Card>

            <Card title="计算说明与凭证" styles={{ body: { paddingTop: 12 } }}>
              <Form.Item name="calc_explanation" label="索赔金额计算说明（将原样打印在纸质单上）">
                <Input.TextArea rows={4} placeholder="描述索赔事实、计算过程（如工时 × 单价）及依据的质量协议条款" />
              </Form.Item>
              <div className="f-note" style={{ marginBottom: 12 }}>
                纸质单固定条款自动打印，无需填写：供应商索赔主要基于<b>交货和质量问题</b>、<b>制造过程中发现质量问题</b>、<b>导致我司客户索赔的质量问题</b>。
              </div>
              <Form.Item name="remarks" label="备注">
                <Input.TextArea rows={2} placeholder="选填" />
              </Form.Item>
              <Form.Item label="附件（检验报告 / 照片等）" style={{ marginBottom: 0 }}>
                <Upload.Dragger multiple fileList={attachments} onChange={({ fileList }: any) => setAttachments(fileList)}
                  customRequest={async (options: any) => {
                    try {
                      const res: any = await fileApi.upload(options.file, 'supplier-claim')
                      options.onSuccess(res.data || res, options.file)
                    } catch (e) { options.onError(e as any) }
                  }}>
                  <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                  <p className="ant-upload-text">点击或拖拽上传附件</p>
                </Upload.Dragger>
              </Form.Item>
            </Card>
          </div>

          <div className="clm-sticky">
            <Card title="纸质单预览" extra={<span className="sc-note">随填写实时更新</span>} styles={{ body: { padding: 12, background: '#f8fafc' } }}>
              <ClaimPaper small claim={preview} />
            </Card>
            <Card title="提交前须知" styles={{ body: { paddingTop: 4 } }}>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: '#475569', lineHeight: 2 }}>
                <li>提交时按<b>当前金额</b>冻结审批链快照：≥ ¥1,000 增加「上级部门意见」节点，≥ ¥5,000 再增加「总经理意见」。</li>
                <li>审批链为 <b>索赔部门 → 上级部门 → 财务结算</b>逐级签字，全部通过后自动归档。</li>
                <li>驳回 / 撤回后可修改重新提交，历史审批记录按轮次留档。</li>
                <li>归档后按纸质单版式<b>打印 / 另存 PDF</b> 存档（草稿亦可预览打印）。</li>
              </ul>
            </Card>
          </div>
        </div>
      </Form>
    </div>
  )
}
