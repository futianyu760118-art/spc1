import { useEffect, useState, useRef, useCallback } from 'react'
import { Modal, Input, Button, Space, Spin, message, Tag } from 'antd'
import { SendOutlined, CopyOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { supplierMessageApi } from '../../../../services/api'
import { useAuthStore } from '../../../../store/auth'

interface MessageItem {
  id: number
  supplier_name: string
  supplier_account: string | null
  sender_id: number
  sender_name: string
  content: string
  po_no: string | null
  created_at: string
}

interface PlanRow {
  id: number
  supplier_name: string | null
  supplier_account: string | null
  po_no: string
  material_code: string
  material_name: string | null
  spec_model: string | null
  unit: string | null
  po_qty: number | null
  received_qty: number | null
  shortage_qty: number | null
  eta: string | null
  order_no: string | null
  owner: string | null
}

interface SupplierChatModalProps {
  open: boolean
  record: PlanRow | null
  onClose: () => void
}

export default function SupplierChatModal({ open, record, onClose }: SupplierChatModalProps) {
  const currentUser = useAuthStore((s) => s.currentUser)
  const [messages, setMessages] = useState<MessageItem[]>([])
  const [loading, setLoading] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const [sending, setSending] = useState(false)
  const chatRef = useRef<HTMLDivElement>(null)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const lastMsgIdRef = useRef<number>(0)

  const supplierName = record?.supplier_name || ''

  const loadMessages = useCallback(async () => {
    if (!supplierName) return
    setLoading(true)
    try {
      const res: any = await supplierMessageApi.list(supplierName, { page: 1, page_size: 100 })
      const items: MessageItem[] = res.data.items || []
      setMessages(items)
      if (items.length > 0) {
        lastMsgIdRef.current = items[items.length - 1].id
      }
    } catch {
      message.error('加载消息失败')
    } finally {
      setLoading(false)
    }
  }, [supplierName])

  useEffect(() => {
    if (open && supplierName) {
      loadMessages()
      pollTimerRef.current = setInterval(async () => {
        try {
          const res: any = await supplierMessageApi.unread(supplierName, lastMsgIdRef.current)
          const newItems: MessageItem[] = res.data.items || []
          if (newItems.length > 0) {
            setMessages(prev => {
              const existingIds = new Set(prev.map(m => m.id))
              const unique = newItems.filter(m => !existingIds.has(m.id))
              if (unique.length > 0) {
                lastMsgIdRef.current = unique[unique.length - 1].id
              }
              return [...prev, ...unique]
            })
          }
        } catch {
          // 轮询失败静默处理
        }
      }, 5000)
    }
    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
        pollTimerRef.current = null
      }
    }
  }, [open, supplierName, loadMessages])

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight
    }
  }, [messages])

  const handleSend = async () => {
    const content = inputValue.trim()
    if (!content || !supplierName) return
    setSending(true)
    try {
      await supplierMessageApi.send({
        supplier_name: supplierName,
        supplier_account: record?.supplier_account || undefined,
        content,
        po_no: record?.po_no || undefined,
      })
      setInputValue('')
      await loadMessages()
    } catch {
      message.error('发送失败')
    } finally {
      setSending(false)
    }
  }

  const buildInitialMessage = () => {
    if (!record) return ''
    return [
      `${record.supplier_name || '供应商'}，您好：`,
      '请确认以下物料的交付安排。',
      `采购单号：${record.po_no || '-'}`,
      `物料：${record.material_code}${record.material_name ? ` / ${record.material_name}` : ''}`,
      `规格型号：${record.spec_model || '-'}`,
      `关联订单：${record.order_no || '-'}`,
      `计划数量：${record.po_qty ?? '-'}${record.unit || ''}`,
      `已收数量：${record.received_qty ?? 0}${record.unit || ''}`,
      `缺料数量：${record.shortage_qty && record.shortage_qty > 0 ? record.shortage_qty : '-'}`,
      `承诺交货日期：${record.eta ? dayjs(record.eta).format('YYYY-MM-DD') : '-'}`,
      '请回复最新交期、可交数量及异常原因，谢谢。',
    ].join('\n')
  }

  const fillTemplate = () => {
    setInputValue(buildInitialMessage())
  }

  const isMine = (msg: MessageItem) => {
    const myId = currentUser?.id
    return msg.sender_id === Number(myId)
  }

  return (
    <Modal
      title={`供应商沟通${record?.supplier_name ? ` - ${record.supplier_name}` : ''}`}
      open={open}
      onCancel={onClose}
      width={680}
      footer={null}
      destroyOnClose
    >
      <div style={{ marginBottom: 12 }}>
        <Space>
          <span style={{ color: '#64748b' }}>供应商账号</span>
          <span>{record?.supplier_account || '-'}</span>
          <span style={{ color: '#64748b', marginLeft: 16 }}>负责人</span>
          <span>{record?.owner || '-'}</span>
        </Space>
      </div>

      <div
        ref={chatRef}
        style={{
          height: 360,
          overflowY: 'auto',
          border: '1px solid #e5e7eb',
          borderRadius: 8,
          padding: '12px 16px',
          marginBottom: 12,
          background: '#f8fafc',
        }}
      >
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 80 }}><Spin /></div>
        ) : messages.length === 0 ? (
          <div style={{ textAlign: 'center', color: '#94a3b8', paddingTop: 80 }}>
            暂无消息，发送第一条消息开始沟通
          </div>
        ) : (
          messages.map((msg) => {
            const mine = isMine(msg)
            return (
              <div
                key={msg.id}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: mine ? 'flex-end' : 'flex-start',
                  marginBottom: 10,
                }}
              >
                <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 2 }}>
                  {msg.sender_name} · {dayjs(msg.created_at).format('MM-DD HH:mm')}
                </div>
                {msg.po_no && (
                  <Tag color="blue" style={{ marginBottom: 4, fontSize: 11 }}>PO: {msg.po_no}</Tag>
                )}
                <div
                  style={{
                    maxWidth: '80%',
                    padding: '8px 14px',
                    borderRadius: mine ? '12px 12px 4px 12px' : '12px 12px 12px 4px',
                    background: mine ? '#1677ff' : '#fff',
                    color: mine ? '#fff' : '#1e293b',
                    border: mine ? 'none' : '1px solid #e5e7eb',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    fontSize: 13,
                    lineHeight: 1.6,
                  }}
                >
                  {msg.content}
                </div>
              </div>
            )
          })
        )}
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <Button icon={<CopyOutlined />} onClick={fillTemplate} size="small">
          填入模板
        </Button>
        <Input.TextArea
          value={inputValue}
          onChange={e => setInputValue(e.target.value)}
          rows={3}
          placeholder="输入消息..."
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSend}
          loading={sending}
          disabled={!inputValue.trim()}
        >
          发送
        </Button>
      </div>
    </Modal>
  )
}