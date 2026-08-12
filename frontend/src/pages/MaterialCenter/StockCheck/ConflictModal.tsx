import { Modal, Descriptions, Tag, Space, Typography } from 'antd'

const { Text } = Typography

export interface ConflictDraft {
  item_id: number
  material_code?: string | null
  material_name?: string | null
  actual_qty?: number | null
  is_checked?: number | null
  remark?: string | null
}

interface Props {
  open: boolean
  myDraft: ConflictDraft | null
  serverVersion: number | null
  serverItem?: Record<string, any> | null
  serverChangedBy?: string | null
  onOverwrite: () => void
  onDiscard: () => void
}

export default function ConflictModal({
  open,
  myDraft,
  serverVersion,
  serverItem,
  serverChangedBy,
  onOverwrite,
  onDiscard,
}: Props) {
  const srvActual = serverItem?.actual_qty ?? null
  const srvChecked = serverItem?.is_checked ?? null
  const srvRemark = serverItem?.remark ?? null
  return (
    <Modal
      open={open}
      title="⚠ 该行已被他人修改"
      okText="用我的覆盖(重试)"
      cancelText="丢弃我的"
      onOk={onOverwrite}
      onCancel={onDiscard}
      okButtonProps={{ danger: true }}
    >
      {myDraft && (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text type="secondary">
            物料:{myDraft.material_code ?? '-'} {myDraft.material_name ?? ''}
          </Text>
          <Tag color="orange">
            服务端最新版本号:v{serverVersion ?? '?'}
            {serverChangedBy ? ` · 最后修改人:${serverChangedBy}` : ''}
          </Tag>
          <Descriptions column={3} size="small" bordered>
            <Descriptions.Item label="">{` `}</Descriptions.Item>
            <Descriptions.Item label="我输入的">我的</Descriptions.Item>
            <Descriptions.Item label="最新值">服务端</Descriptions.Item>
            <Descriptions.Item label="实盘数">值</Descriptions.Item>
            <Descriptions.Item>{myDraft.actual_qty ?? '(空)'}</Descriptions.Item>
            <Descriptions.Item>{srvActual ?? '(空)'}</Descriptions.Item>
            <Descriptions.Item label="已盘">标记</Descriptions.Item>
            <Descriptions.Item>{myDraft.is_checked === 1 ? '是' : '否'}</Descriptions.Item>
            <Descriptions.Item>{srvChecked === 1 ? '是' : '否'}</Descriptions.Item>
            <Descriptions.Item label="备注">文本</Descriptions.Item>
            <Descriptions.Item>{myDraft.remark || '(空)'}</Descriptions.Item>
            <Descriptions.Item>{srvRemark || '(空)'}</Descriptions.Item>
          </Descriptions>
          <Text type="secondary">
            点"用我的覆盖"将以服务端最新版本号重试保存;点"丢弃我的"采用服务端值。
          </Text>
        </Space>
      )}
    </Modal>
  )
}
