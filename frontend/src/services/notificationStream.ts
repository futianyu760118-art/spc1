// 跨页签共享的通知 SSE 连接。
// 背景: HTTP/1.1 下浏览器对同源只有 6 条并发连接(所有页签共享)。此前 MainLayout
// 和通知页各自为每个页签开一条常驻 SSE, 开 5~6 个页签即耗尽预算, 页面数据请求
// 全部排队 -> "多开页面加载不出"。
// 方案: localStorage 租约选主, 整个浏览器只有 leader 页签持有一条 SSE, 事件经
// BroadcastChannel 广播给所有页签。不能用 Web Locks: 它仅在安全上下文(HTTPS/
// localhost)可用, 本系统经局域网 IP / HTTP 访问时 navigator.locks 是 undefined。
// 无 localStorage/BroadcastChannel 的环境退回每页签自连(旧行为兜底)。

export type NotificationStreamEvent =
  | { type: 'unread'; data: Record<string, unknown> }
  | { type: 'connected' }
  | { type: 'degraded' }

type Listener = (event: NotificationStreamEvent) => void
type LeaderRecord = { id: string; at: number }

const CHANNEL_NAME = 'spc-notification-stream'
const LEADER_KEY = 'spc-notification-stream-leader'
const HEARTBEAT_MS = 5000
const LEASE_MS = 20000

function readLeader(): LeaderRecord | null {
  try {
    return JSON.parse(localStorage.getItem(LEADER_KEY) || 'null') as LeaderRecord | null
  } catch {
    return null
  }
}

function storageWritable(): boolean {
  try {
    localStorage.setItem(LEADER_KEY, '__probe__')
    localStorage.removeItem(LEADER_KEY)
    return true
  } catch {
    return false
  }
}

class NotificationStreamHub {
  private refCount = 0
  private token = ''
  private tabId = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  private isLeaderFlag = false
  private listeners = new Set<Listener>()
  private channel: BroadcastChannel | null = null
  private es: EventSource | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null

  private readonly onStorage = (ev: StorageEvent) => {
    // leader 页签关闭/让位会显式删除租约: 少量随机延迟后抢主, 不必等租约超时
    if (ev.key === LEADER_KEY && ev.newValue === null && !this.isLeaderFlag) {
      setTimeout(() => this.elect(), Math.floor(Math.random() * 200))
    }
  }

  private readonly onVisibility = () => {
    if (document.visibilityState === 'visible') {
      this.elect()
    } else if (this.isLeaderFlag) {
      // 隐藏页签不需要实时流, 让位给可见页签, 避免后台页签占着连接
      this.resign()
    }
  }

  private readonly onPageHide = () => {
    if (this.isLeaderFlag) {
      try { localStorage.removeItem(LEADER_KEY) } catch { /* silent */ }
    }
  }

  subscribe(token: string, listener: Listener): () => void {
    if (this.refCount === 0) {
      this.start(token)
    } else if (token !== this.token) {
      this.restart(token)
    }
    this.refCount += 1
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
      this.refCount -= 1
      if (this.refCount <= 0) this.stop()
    }
  }

  private start(token: string): void {
    this.token = token
    try {
      this.channel = new BroadcastChannel(CHANNEL_NAME)
      this.channel.onmessage = (ev: MessageEvent) => this.emitLocal(ev.data as NotificationStreamEvent)
    } catch {
      this.channel = null
    }
    if (this.channel && storageWritable()) {
      window.addEventListener('storage', this.onStorage)
      window.addEventListener('pagehide', this.onPageHide)
      document.addEventListener('visibilitychange', this.onVisibility)
      this.heartbeatTimer = setInterval(() => this.elect(), HEARTBEAT_MS)
      this.elect()
    } else {
      this.openStream()
    }
  }

  private restart(token: string): void {
    // 本页签换 token(重新登录): leader 需要用新 token 重连; 非 leader 无本地连接可动,
    // 若 leader 在别的页签仍是旧 token, 其 SSE 会 401 -> degraded -> 各页签轮询兜底。
    this.token = token
    this.closeStream()
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.isLeader()) this.openStream()
  }

  private stop(): void {
    this.closeStream()
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
    window.removeEventListener('storage', this.onStorage)
    window.removeEventListener('pagehide', this.onPageHide)
    document.removeEventListener('visibilitychange', this.onVisibility)
    this.onPageHide()
    this.isLeaderFlag = false
    if (this.channel) {
      try { this.channel.close() } catch { /* silent */ }
      this.channel = null
    }
    this.listeners.clear()
    this.token = ''
  }

  private elect(): void {
    if (this.refCount <= 0) return
    const now = Date.now()
    const leader = readLeader()
    if (leader && leader.id !== this.tabId && leader.at > now - LEASE_MS) {
      // 有效租约属于别人: 若因并发竞争短暂双主, 此处退位自愈
      if (this.isLeaderFlag) this.resign()
      return
    }
    if (this.isLeaderFlag) {
      try { localStorage.setItem(LEADER_KEY, JSON.stringify({ id: this.tabId, at: now })) } catch { /* silent */ }
      return
    }
    try {
      localStorage.setItem(LEADER_KEY, JSON.stringify({ id: this.tabId, at: now }))
    } catch {
      return
    }
    // 并发抢主裁决: 重读确认最终写入者是自己, 失败等下轮
    const cur = readLeader()
    if (!cur || cur.id !== this.tabId) return
    this.isLeaderFlag = true
    this.openStream()
  }

  private resign(): void {
    this.isLeaderFlag = false
    this.closeStream()
    try { localStorage.removeItem(LEADER_KEY) } catch { /* silent */ }
  }

  private isLeader(): boolean {
    return this.isLeaderFlag || this.heartbeatTimer === null
  }

  private openStream(): void {
    if (this.es || this.reconnectTimer) return
    try {
      this.es = new EventSource(`/api/v1/notifications/stream?token=${encodeURIComponent(this.token)}`)
    } catch {
      this.scheduleReconnect()
      return
    }
    this.es.addEventListener('open', () => this.broadcast({ type: 'connected' }))
    this.es.addEventListener('unread', (ev) => {
      let data: Record<string, unknown> = {}
      try { data = JSON.parse((ev as MessageEvent).data) } catch { /* 坏帧丢弃 */ }
      this.broadcast({ type: 'unread', data })
    })
    this.es.addEventListener('degraded', () => this.broadcast({ type: 'degraded' }))
    this.es.addEventListener('recovered', () => this.broadcast({ type: 'connected' }))
    this.es.addEventListener('error', () => {
      this.closeStream()
      this.broadcast({ type: 'degraded' })
      this.scheduleReconnect()
    })
  }

  private closeStream(): void {
    if (!this.es) return
    try { this.es.close() } catch { /* silent */ }
    this.es = null
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      if (this.isLeader()) this.openStream()
    }, 30000)
  }

  private broadcast(event: NotificationStreamEvent): void {
    // BroadcastChannel 不回环到发送方所在的页签, 所以本地也要派发一份
    this.emitLocal(event)
    try { this.channel?.postMessage(event) } catch { /* silent */ }
  }

  private emitLocal(event: NotificationStreamEvent): void {
    this.listeners.forEach((listener) => listener(event))
  }
}

export const notificationStream = new NotificationStreamHub()
