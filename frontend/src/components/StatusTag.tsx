import { Tag } from 'antd'

const statusConfig: Record<string, { color: string; label: string }> = {
  open: { color: 'red', label: '待处理' },
  in_progress: { color: 'orange', label: '处理中' },
  closed: { color: 'green', label: '已关闭' },
  placed: { color: 'blue', label: '已下单' },
  accepted: { color: 'cyan', label: '已接收' },
  in_production: { color: 'orange', label: '在产' },
  shipped: { color: 'purple', label: '已发货' },
  received: { color: 'green', label: '已收料' },
}

interface StatusTagProps {
  status: string
}

export default function StatusTag({ status }: StatusTagProps) {
  const cfg = statusConfig[status]
  return cfg ? <Tag color={cfg.color}>{cfg.label}</Tag> : <Tag>{status}</Tag>
}
