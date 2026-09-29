import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button, Card, Form, Popconfirm, Spin, message } from 'antd'
import { ArrowLeftOutlined, SaveOutlined, SendOutlined } from '@ant-design/icons'
import { getBusiness } from './businesses'
import FormEngine from './engine/FormEngine'

export default function ApprovalCreateForm() {
  const { bizType, id } = useParams()
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const business = bizType ? getBusiness(bizType) : undefined
  const numericId = id ? Number(id) : undefined
  const editId = numericId !== undefined && Number.isFinite(numericId) ? numericId : undefined

  useEffect(() => {
    if (!business) return
    form.setFieldsValue(business.adapter.initialValues || {})
    if (!editId) return
    setLoading(true)
    ;(async () => {
      try {
        const values = await business.adapter.loadForEdit(editId)
        form.setFieldsValue(values)
      } catch { /* 全局拦截器已提示 */ } finally { setLoading(false) }
    })()
  }, [bizType, editId]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!business) {
    return (
      <div className="sc-page">
        <Card>未注册的发起业务：{bizType}</Card>
      </div>
    )
  }

  const doSave = async (isSubmit: boolean) => {
    try {
      const values = await form.validateFields()
      setSaving(true)
      const res = isSubmit
        ? await business.adapter.submit(values, editId)
        : await business.adapter.saveDraft(values, editId)
      message.success(isSubmit ? '已提交审批' : '草稿已保存')
      if (isSubmit) {
        navigate(`/approvals/items/${business.bizType}/${res.id}`)
      } else {
        navigate(`/approvals/create/${business.bizType}/${res.id}`, { replace: true })
      }
    } catch (error: any) {
      if (error?.errorFields) return // 表单校验失败，AntD 已在字段上提示
      // 业务错误由全局拦截器提示
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="sc-page">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/approvals/create')}>返回</Button>
        <div style={{ fontSize: 18, fontWeight: 600 }}>
          {editId ? `编辑${business.schema.title}` : `新建${business.schema.title}`}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          {business.schema.actions.draft ? (
            <Button icon={<SaveOutlined />} loading={saving} onClick={() => doSave(false)}>仅存草稿</Button>
          ) : null}
          <Popconfirm title="提交审批" description="提交后进入审批链，确认提交？"
            onConfirm={() => doSave(true)} okText="确认提交" cancelText="再检查一下">
            <Button type="primary" icon={<SendOutlined />} loading={saving}>保存并提交审批</Button>
          </Popconfirm>
        </div>
      </div>
      <Spin spinning={loading}>
        <FormEngine schema={business.schema} form={form} />
      </Spin>
    </div>
  )
}
