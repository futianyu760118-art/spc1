import { useState } from 'react'
import { Button, Modal, Select, Input, message, Space, Typography, Checkbox } from 'antd'
import { ShareAltOutlined, CopyOutlined, LinkOutlined } from '@ant-design/icons'
import { useLocation } from 'react-router-dom'
import { shareApi } from '../../services/api'

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

export default function ShareButton() {
  const [open, setOpen] = useState(false)
  const [expiresIn, setExpiresIn] = useState<string>('30d')
  const [permissions, setPermissions] = useState<string[]>(['read'])
  const [shareUrl, setShareUrl] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const location = useLocation()

  const handleCreate = async () => {
    setLoading(true)
    try {
      const res: any = await shareApi.create({
        target_path: location.pathname,
        expires_in: expiresIn,
        permissions,
      })
      const fullUrl = `${window.location.origin}${res.data.share_url}`
      setShareUrl(fullUrl)
      message.success('分享链接已生成')
    } catch (e: any) {
      message.error(e?.message || '生成分享链接失败')
    }
    setLoading(false)
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(shareUrl).then(() => {
      message.success('链接已复制到剪贴板')
    }).catch(() => {
      const input = document.createElement('input')
      input.value = shareUrl
      document.body.appendChild(input)
      input.select()
      document.execCommand('copy')
      document.body.removeChild(input)
      message.success('链接已复制到剪贴板')
    })
  }

  const handleOpen = () => {
    setShareUrl('')
    setExpiresIn('30d')
    setPermissions(['read'])
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
        width={480}
      >
        <div style={{ marginTop: 16 }}>
          <div style={{ marginBottom: 16 }}>
            <Text type="secondary" style={{ fontSize: 'calc(0.8125rem * var(--font-size-scale))' }}>
              当前页面路径
            </Text>
            <Input
              value={location.pathname}
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

          {!shareUrl ? (
            <Button
              type="primary"
              icon={<ShareAltOutlined />}
              onClick={handleCreate}
              loading={loading}
              disabled={permissions.length === 0}
              block
              style={{ fontSize: 'calc(0.875rem * var(--font-size-scale))' }}
            >
              生成分享链接
            </Button>
          ) : (
            <div>
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
                他人点击此链接可直接访问该页面（权限：{permissions.map(p => PERMISSION_OPTIONS.find(o => o.value === p)?.label).join('、')}）
              </Text>
            </div>
          )}
        </div>
      </Modal>
    </>
  )
}
