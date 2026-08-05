import { useState, useEffect, useMemo } from 'react'
import { Button, Modal, Select, Input, message, Space, Typography, Checkbox, Divider, Alert, List, AutoComplete } from 'antd'
import { ShareAltOutlined, CopyOutlined, LinkOutlined, SendOutlined } from '@ant-design/icons'
import { useLocation } from 'react-router-dom'
import { shareApi, wecomApi, WecomUser, ShareCreateRecipient } from '../../services/api'
import { usePermissionStore } from '../../store/permission'
import { WecomRecipientPicker, WecomRecipientValue } from '../WecomRecipientPicker'

const { Text } = Typography

const EXPIRES_OPTIONS = [
  { value: '7d', label: '7天' },
  { value: '30d', label: '30天' },
  { value: '90d', label: '90天' },
  { value: 'permanent', label: '永久' },
]

const PERMISSION_OPTIONS = [
  { label: '查看', value: 'read' },
  { label: '新增', value: 'create' },
  { label: '修改', value: 'update' },
  { label: '删除', value: 'delete' },
]

const REASON_OPTIONS = [
  '请审阅',
  '请确认',
  '协同处理',
  '仅供查看',
  '其他',
]

function findPageName(nodes: any[], pathname: string): string | null {
  for (const node of nodes) {
    if (node.route_path && pathname.startsWith(node.route_path)) {
      return node.name
    }
    if (node.children?.length) {
      const name = findPageName(node.children, pathname)
      if (name) return name
    }
  }
  return null
}

export default function ShareButton() {
  const [open, setOpen] = useState(false)
  const [expiresIn, setExpiresIn] = useState<string>('30d')
  const [permissions, setPermissions] = useState<string[]>(['read'])
  const [reason, setReason] = useState<string | undefined>(undefined)
  const [shareUrl, setShareUrl] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [wecomUsers, setWecomUsers] = useState<WecomUser[]>([])
  const [wecomLoadError, setWecomLoadError] = useState<string | null>(null)
  const [wecomLoading, setWecomLoading] = useState(false)
  const [wecomRecipient, setWecomRecipient] = useState<WecomRecipientValue>({ user_ids: [] })
  const [wecomDelivery, setWecomDelivery] = useState<{ success: number; failed: { recipient_id: string; error_msg: string }[] } | null>(null)
  const location = useLocation()
  const permTree = usePermissionStore(s => s.tree)

  const pageName = useMemo(() => findPageName(permTree, location.pathname), [permTree, location.pathname])

  useEffect(() => {
    if (!open) return
    if (wecomUsers.length || wecomLoading) return
    setWecomLoading(true)
    wecomApi.listUsers()
      .then((res: any) => setWecomUsers(res?.data || []))
      .catch((e) => setWecomLoadError(e?.response?.data?.message || e?.message || '企业微信未配置或加载失败'))
      .finally(() => setWecomLoading(false))
  }, [open])

  const hasRecipients = wecomRecipient.user_ids.length > 0

  const handleGenerateAndSend = async () => {
    setLoading(true)
    try {
      const res: any = await shareApi.create({
        target_path: location.pathname,
        expires_in: expiresIn,
        permissions,
        reason: reason || undefined,
        auto_send_wecom: hasRecipients,
        recipient: hasRecipients ? (wecomRecipient as ShareCreateRecipient) : undefined,
      })
      const data = res?.data ?? res
      const fullUrl = `${window.location.origin}${data.share_url}`
      setShareUrl(fullUrl)
      const delivery = data?.wecom_delivery ?? null
      setWecomDelivery(delivery)
      if (hasRecipients) {
        if (delivery?.failed?.length) {
          message.warning(`已发送：成功 ${delivery.success} 条，失败 ${delivery.failed.length} 条`)
        } else {
          message.success(`已发送：成功 ${delivery?.success ?? 0} 条`)
        }
      } else {
        message.success('分享链接已生成')
      }
    } catch (e: any) {
      message.error(e?.response?.data?.message || e?.message || '操作失败')
    }
    setLoading(false)
  }

  const handleCopy = () => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(shareUrl).then(() => {
        message.success('链接已复制到剪贴板')
      }).catch(() => {
        fallbackCopy()
      })
    } else {
      fallbackCopy()
    }
  }

  const fallbackCopy = () => {
    const input = document.createElement('input')
    input.value = shareUrl
    document.body.appendChild(input)
    input.select()
    document.execCommand('copy')
    document.body.removeChild(input)
    message.success('链接已复制到剪贴板')
  }

  const handleOpen = () => {
    setShareUrl('')
    setExpiresIn('30d')
    setPermissions(['read'])
    setReason(undefined)
    setWecomDelivery(null)
    setWecomRecipient({ user_ids: [] })
    setOpen(true)
  }

  return (
    <>
      <Button
        type="text"
        icon={<ShareAltOutlined />}
        onClick={handleOpen}
        style={{ fontSize: 'calc(0.875rem * var(--font-size-scale))', width: 36, height: 36, borderRadius: 10, color: '#64748b' }}
        title="分享当前页面"
      />
      <Modal
        title={<Space><LinkOutlined /> 分享当前页面</Space>}
        open={open}
        onCancel={() => setOpen(false)}
        footer={null}
        width={560}
      >
        <div style={{ marginTop: 16 }}>
          <div style={{ marginBottom: 16 }}>
            <Text type="secondary" style={{ fontSize: 'calc(0.8125rem * var(--font-size-scale))' }}>
              当前页面
            </Text>
            <Input
              value={pageName || location.pathname}
              readOnly
              style={{ marginTop: 4, fontSize: 'calc(0.875rem * var(--font-size-scale))' }}
            />
          </div>

          <div style={{ marginBottom: 16 }}>
            <Text type="secondary" style={{ fontSize: 'calc(0.8125rem * var(--font-size-scale))' }}>
              分享权限
            </Text>
            <div style={{ marginTop: 4 }}>
              <Checkbox.Group
                options={PERMISSION_OPTIONS}
                value={permissions}
                onChange={(vals) => setPermissions(vals as string[])}
                disabled={!!shareUrl}
              />
            </div>
            <Text type="secondary" style={{ fontSize: 'calc(0.75rem * var(--font-size-scale))', marginTop: 4, display: 'block' }}>
              选择允许分享用户执行的操作
            </Text>
          </div>

          <div style={{ marginBottom: 16 }}>
            <Text type="secondary" style={{ fontSize: 'calc(0.8125rem * var(--font-size-scale))' }}>
              有效期
            </Text>
            <Select
              value={expiresIn}
              onChange={setExpiresIn}
              options={EXPIRES_OPTIONS}
              style={{ width: '100%', marginTop: 4 }}
              disabled={!!shareUrl}
            />
          </div>

          <div style={{ marginBottom: 16 }}>
            <Text type="secondary" style={{ fontSize: 'calc(0.8125rem * var(--font-size-scale))' }}>
              分享原因（选填）
            </Text>
            <AutoComplete
              value={reason}
              onChange={setReason}
              placeholder="请选择或输入分享原因"
              allowClear
              options={REASON_OPTIONS.map(r => ({ label: r, value: r }))}
              style={{ width: '100%', marginTop: 4 }}
              disabled={!!shareUrl}
            />
          </div>

          <Divider style={{ margin: '12px 0' }} />

          <div style={{ marginBottom: 16 }}>
            <Text type="secondary" style={{ fontSize: 'calc(0.8125rem * var(--font-size-scale))' }}>
              企业微信收件人（选填）
            </Text>
            <div style={{ marginTop: 8 }}>
              {wecomLoadError && (
                <Alert
                  type="warning"
                  message={wecomLoadError}
                  showIcon
                  style={{ marginBottom: 12 }}
                />
              )}
              <WecomRecipientPicker
                value={wecomRecipient}
                onChange={setWecomRecipient}
                userOptions={wecomUsers}
                loading={wecomLoading}
              />
            </div>
          </div>

          <div style={{ marginTop: 16, padding: 12, border: '1px solid #eee', borderRadius: 6 }}>
            <div style={{ fontWeight: 600 }}>{pageName || '页面分享'}</div>
            <div style={{ color: '#666', marginTop: 4 }}>{location.pathname}</div>
            <div style={{ color: '#999', marginTop: 4, fontSize: 'calc(0.75rem * var(--font-size-scale))' }}>
              权限：{permissions.map(p => PERMISSION_OPTIONS.find(o => o.value === p)?.label).join('、')}
            </div>
          </div>

          {wecomDelivery && (
            <Alert
              style={{ marginTop: 12 }}
              type={wecomDelivery.failed.length ? 'warning' : 'success'}
              message={`成功 ${wecomDelivery.success} 条，失败 ${wecomDelivery.failed.length} 条`}
              description={
                wecomDelivery.failed.length ? (
                  <List
                    size="small"
                    dataSource={wecomDelivery.failed}
                    renderItem={(it: any) => (
                      <List.Item>{it.recipient_id}：{it.error_msg}</List.Item>
                    )}
                  />
                ) : null
              }
              showIcon
            />
          )}

          <div style={{ marginTop: 16 }}>
            <Button
              type="primary"
              icon={hasRecipients ? <SendOutlined /> : <ShareAltOutlined />}
              onClick={handleGenerateAndSend}
              loading={loading}
              disabled={permissions.length === 0}
              block
              style={{ fontSize: 'calc(0.875rem * var(--font-size-scale))' }}
            >
              {hasRecipients ? '生成并发送' : '生成分享链接'}
            </Button>
          </div>

          {shareUrl && (
            <div style={{ marginTop: 16 }}>
              <Text type="secondary" style={{ fontSize: 'calc(0.8125rem * var(--font-size-scale))' }}>
                分享链接
              </Text>
              <Input.Search
                value={shareUrl}
                readOnly
                enterButton={<CopyOutlined />}
                onSearch={handleCopy}
                style={{ marginTop: 4, fontSize: 'calc(0.875rem * var(--font-size-scale))' }}
              />
              <Text type="secondary" style={{ fontSize: 'calc(0.75rem * var(--font-size-scale))', marginTop: 8, display: 'block' }}>
                他人点击此链接可直接访问该页面
              </Text>
            </div>
          )}
        </div>
      </Modal>
    </>
  )
}
