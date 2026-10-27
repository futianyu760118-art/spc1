import React, { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Checkbox, Descriptions, Divider, Drawer, Empty, Space, Tag, Typography } from 'antd'
import type { AgentCapability } from '../../services/agent'

const { Text } = Typography

interface Detail {
  agent?: { id: number; display_name: string; username?: string; status: string }
  policy?: { granted: string[]; disabled: string[]; data_scope: { mode: string; org_ids: number[]; include_sub: boolean } }
  scope?: { summary: string; org_names: string[] }
  effective_capabilities?: AgentCapability[]
  role_baseline?: AgentCapability[]
  grantable?: AgentCapability[]
  catalog?: AgentCapability[]
}

interface Props {
  open: boolean
  detail?: Detail | null
  loading?: boolean
  saving?: boolean
  onClose: () => void
  onSave: (data: { granted: string[]; disabled: string[] }) => void
}

export const CapabilityPolicyDrawer: React.FC<Props> = ({ open, detail, loading, saving, onClose, onSave }) => {
  const [granted, setGranted] = useState<Set<string>>(new Set())
  const [disabled, setDisabled] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (!open || !detail?.policy) return
    setGranted(new Set(detail.policy.granted || []))
    setDisabled(new Set(detail.policy.disabled || []))
  }, [open, detail])

  const groups = useMemo(() => {
    const catalog = detail?.catalog || []
    return {
      roleOwned: catalog.filter(item => item.role_owned),
      grantable: catalog.filter(item => item.grantable_now && !item.role_owned),
      locked: catalog.filter(item => !item.role_owned && !item.grantable_now),
    }
  }, [detail])

  const toggle = (setter: React.Dispatch<React.SetStateAction<Set<string>>>, code: string, checked: boolean) => {
    setter(prev => {
      const next = new Set(prev)
      if (checked) next.add(code)
      else next.delete(code)
      return next
    })
  }

  return (
    <Drawer
      title={detail?.agent ? `配置 ${detail.agent.display_name}` : '配置子智能体'}
      width={560}
      open={open}
      onClose={onClose}
      extra={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button
            type="primary"
            loading={saving}
            onClick={() => onSave({ granted: Array.from(granted), disabled: Array.from(disabled) })}
          >
            保存
          </Button>
        </Space>
      }
    >
      {loading ? <div style={{ padding: 24, textAlign: 'center' }}>加载中...</div> : !detail ? <Empty /> : (
        <>
          <Descriptions size="small" column={1} bordered>
            <Descriptions.Item label="当前生效范围">{detail.scope?.summary || '本人数据'}</Descriptions.Item>
            <Descriptions.Item label="数据范围配置">
              {detail.policy?.data_scope?.mode || 'org'}
              {detail.policy?.data_scope?.org_ids?.length ? `（额外组织 ${detail.policy.data_scope.org_ids.length} 个）` : ''}
            </Descriptions.Item>
            <Descriptions.Item label="当前生效能力">
              {(detail.effective_capabilities || []).map(item => <Tag key={item.code} color="blue">{item.name}</Tag>)}
            </Descriptions.Item>
          </Descriptions>
          <Alert
            style={{ marginTop: 12 }}
            type="info"
            showIcon
            message="P1 主管只能配置能力；数据范围由管理员配置。授予项不得超过主管自身能力。"
          />

          <Divider orientation="left">角色已有能力（可禁用收紧）</Divider>
          {groups.roleOwned.length === 0 ? <Text type="secondary">无</Text> : (
            <Space direction="vertical" style={{ width: '100%' }}>
              {groups.roleOwned.map(item => (
                <Checkbox
                  key={item.code}
                  checked={!disabled.has(item.code)}
                  onChange={e => toggle(setDisabled, item.code, !e.target.checked)}
                >
                  {item.name}
                  <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>{item.code}</Text>
                </Checkbox>
              ))}
            </Space>
          )}

          <Divider orientation="left">我可授予的能力</Divider>
          {groups.grantable.length === 0 ? <Text type="secondary">无</Text> : (
            <Space direction="vertical" style={{ width: '100%' }}>
              {groups.grantable.map(item => (
                <Checkbox
                  key={item.code}
                  checked={granted.has(item.code)}
                  onChange={e => toggle(setGranted, item.code, e.target.checked)}
                >
                  {item.name}
                  <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>{item.code}</Text>
                </Checkbox>
              ))}
            </Space>
          )}

          <Divider orientation="left">不可用（锁定）</Divider>
          {groups.locked.length === 0 ? <Text type="secondary">无</Text> : (
            <Space wrap>
              {groups.locked.map(item => (
                <Tag key={item.code} title={item.description}>{item.name}</Tag>
              ))}
            </Space>
          )}
        </>
      )}
    </Drawer>
  )
}
