import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert, Button, Card, Collapse, Input, Modal, Popconfirm, Select, Space, Steps, Switch, Table, Tag, Tooltip, Typography, message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  DatabaseOutlined, DeleteOutlined, FileZipOutlined,
  LoadingOutlined, QuestionCircleOutlined, ReloadOutlined, RollbackOutlined, SafetyOutlined, SettingOutlined,
} from '@ant-design/icons'
import {
  backupApi, downloadBackup,
  type BackupConfigVo, type BackupJobVo, type BackupRecordRow, type BackupStats,
} from '../../../services/backup'
import { useAuthStore } from '../../../store/auth'

const { Text } = Typography

const SOURCE_LABEL: Record<string, { text: string; color: string }> = {
  manual: { text: '手动', color: 'blue' },
  scheduled: { text: '定时', color: 'green' },
  safety: { text: '恢复前快照', color: 'orange' },
}

const STATUS_LABEL: Record<string, { text: string; color: string }> = {
  running: { text: '进行中', color: 'processing' },
  success: { text: '成功', color: 'success' },
  failed: { text: '失败', color: 'error' },
  deleted: { text: '已删除', color: 'default' },
}

function fmtSize(bytes: number): string {
  if (!bytes) return '-'
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 / 1024).toFixed(1)}MB`
  return `${(bytes / 1024 ** 3).toFixed(2)}GB`
}

function fmtElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  return s < 60 ? `${s} 秒` : `${Math.floor(s / 60)} 分 ${s % 60} 秒`
}

/** 进度弹窗各步骤的通俗说明（key 与 backup_service 的步骤名一致） */
const STEP_DESC: Record<string, Record<string, string>> = {
  backup: {
    '空间预检查': '检查服务器磁盘剩余空间是否足够',
    '数据库备份': '导出数据库中的全部业务数据',
    '附件打包': '打包全部上传文件（图纸、文档等）',
    '完整性校验': '计算校验和，确保备份文件完整、可用于恢复',
    '保留策略清理': '按设置的保留份数自动清理最旧的备份',
  },
  restore: {
    '恢复前预检': '核对备份文件存在且未损坏，此步骤不会改动任何数据',
    '安全快照': '先把当前数据自动备份一份，万一恢复出问题可用于回退',
    '进入维护模式': '暂停所有业务访问和后台任务',
    '数据库恢复': '将数据库整体恢复到所选备份的时间点',
    '附件恢复': '恢复全部上传文件（图纸、文档等）',
    '退出维护模式': '恢复系统正常访问',
  },
}

/** 技术性失败信息 → 管理者能看懂的说法；未命中的失败信息本身已是通俗描述，直接展示原文 */
const FAIL_EXPLAIN: { prefix: string; text: string }[] = [
  { prefix: 'pg_dump 失败', text: '数据库导出失败，常见原因是数据库连接异常或磁盘写入失败；本次未生成备份，现有数据不受影响' },
  { prefix: 'uploads 目录不存在', text: '服务器上找不到附件目录，请联系系统管理员检查部署' },
  { prefix: 'uploads 打包失败', text: '附件打包失败；本次未生成备份，现有数据不受影响' },
  { prefix: '备份异常', text: '备份过程中出现未预期的错误' },
  { prefix: '备份文件缺失', text: '所选备份的文件在服务器上找不到，可能已被移动或删除' },
  { prefix: 'pg_restore 失败', text: '数据库恢复失败，请立即联系系统管理员，可用列表中「恢复前快照」来源的备份回退' },
  { prefix: '附件恢复失败', text: '附件恢复失败，请立即联系系统管理员处理' },
  { prefix: '恢复异常', text: '恢复过程中出现未预期的错误，请立即联系系统管理员' },
  { prefix: '退出维护模式失败', text: '恢复已结束但系统未能自动恢复访问，需要系统管理员按技术日志提示人工处理' },
]

function explainFailure(raw: string): { summary: string; detail: string | null } {
  const hit = FAIL_EXPLAIN.find((f) => raw.startsWith(f.prefix))
  return hit ? { summary: hit.text, detail: raw } : { summary: raw, detail: null }
}

const STEP_STATUS_MAP: Record<string, 'wait' | 'process' | 'finish' | 'error'> = {
  pending: 'wait', running: 'process', ok: 'finish', fail: 'error',
}

const EMPTY_JOB: BackupJobVo = { job_id: '', type: 'backup', status: 'running', steps: [], logs: [], result: null }

/** 备份范围说明（口径与 backup_service 实际行为一致：pg_dump 全库 + uploads 打包，其余不落备份） */
const BACKUP_SCOPE_TIP = (
  <div style={{ maxWidth: 320 }}>
    <div><b>备份包含</b></div>
    <ul style={{ paddingLeft: 18, margin: '4px 0 8px' }}>
      <li>数据库：PostgreSQL 全库（业务数据、系统配置、账号与权限）</li>
      <li>附件：uploads 目录全部上传文件（图纸、文档等）</li>
      <li>每份备份 = 库 + 附件双文件，均记录 sha256 校验和，恢复前自动校验</li>
    </ul>
    <div><b>备份不包含</b></div>
    <ul style={{ paddingLeft: 18, margin: '4px 0' }}>
      <li>服务器环境与密钥配置（.env、部署文件），需另行在服务器侧备份</li>
      <li>Redis 缓存数据（登录黑名单等临时数据，可自动重建）</li>
    </ul>
  </div>
)

export default function BackupPage() {
  const hasPermission = useAuthStore((s: any) => s.hasPermission) as (r: string, a: string) => boolean
  const canManage = hasPermission('backup', 'manage')
  const canView = hasPermission('backup', 'read')

  const [loading, setLoading] = useState(false)
  const [rows, setRows] = useState<BackupRecordRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [stats, setStats] = useState<BackupStats | null>(null)
  const [latestId, setLatestId] = useState<number | null>(null)

  const [job, setJob] = useState<BackupJobVo>(EMPTY_JOB)
  const [jobOpen, setJobOpen] = useState(false)
  const [jobTitle, setJobTitle] = useState('')
  const pollRef = useRef<number | null>(null)

  const [configOpen, setConfigOpen] = useState(false)
  const [config, setConfig] = useState<BackupConfigVo | null>(null)
  const [savingConfig, setSavingConfig] = useState(false)

  const [restoreTarget, setRestoreTarget] = useState<BackupRecordRow | null>(null)
  const [confirmText, setConfirmText] = useState('')
  const [restoring, setRestoring] = useState(false)

  const jobStartRef = useRef<number>(Date.now())
  const [, setJobTick] = useState(0) // 任务进行中每秒触发重渲染，刷新「已进行」时长
  const [logOpenKeys, setLogOpenKeys] = useState<string[]>([])
  const logBoxRef = useRef<HTMLDivElement | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await backupApi.list({ page, page_size: pageSize })
      setRows(res.items)
      setTotal(res.total)
      setStats(res.stats)
      const first = res.items.find((r) => r.status === 'success')
      setLatestId(first ? first.id : null)
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setLoading(false)
    }
  }, [page, pageSize])

  useEffect(() => { if (canView) refresh() }, [refresh, canView])

  const stopPolling = () => {
    if (pollRef.current) { window.clearInterval(pollRef.current); pollRef.current = null }
  }
  useEffect(() => stopPolling, [])

  // 任务进行中每秒重算「已进行」时长（同 FeedbackManagement 进度 ticker 模式）
  useEffect(() => {
    if (!jobOpen || job.status !== 'running') return
    const t = window.setInterval(() => setJobTick((v) => v + 1), 1000)
    return () => window.clearInterval(t)
  }, [jobOpen, job.status])

  // 技术日志有新增或展开时滚到底部，便于看最新输出
  useEffect(() => {
    const el = logBoxRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [job.logs.length, logOpenKeys])

  const startJobPolling = useCallback((jobId: string) => {
    stopPolling()
    pollRef.current = window.setInterval(async () => {
      try {
        const j = await backupApi.job(jobId)
        setJob(j)
        if (j.status !== 'running') {
          stopPolling()
          if (j.status === 'ok') message.success(j.type === 'restore' ? '恢复完成，建议刷新页面' : '备份完成')
          else message.error(j.type === 'restore' ? '恢复失败，请查看日志' : '备份失败，请查看日志')
          refresh()
        }
      } catch {
        // 恢复进入维护模式瞬间业务请求可能 503；jobs 端点在白名单内，一般不受影响，忽略单次失败
      }
    }, 2000)
  }, [refresh])

  const openJobModal = useCallback(async (jobId: string, title: string) => {
    jobStartRef.current = Date.now()
    setLogOpenKeys([])
    setJob(EMPTY_JOB)
    setJobTitle(title)
    setJobOpen(true)
    try { setJob(await backupApi.job(jobId)) } catch { /* 首次拉取失败由轮询兜底 */ }
    startJobPolling(jobId)
  }, [startJobPolling])

  const closeJobModal = () => {
    stopPolling()
    setJobOpen(false)
    refresh()
  }

  const runBackup = async () => {
    const { job_id } = await backupApi.run()
    openJobModal(job_id, '备份进度')
  }

  const openConfig = async () => {
    setConfig(await backupApi.config())
    setConfigOpen(true)
  }

  const saveConfig = async () => {
    if (!config) return
    setSavingConfig(true)
    try {
      await backupApi.saveConfig(config)
      message.success('定时配置已保存')
      setConfigOpen(false)
      refresh()
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setSavingConfig(false)
    }
  }

  const submitRestore = async () => {
    if (!restoreTarget) return
    setRestoring(true)
    try {
      const { job_id } = await backupApi.restore(restoreTarget.id, confirmText)
      setRestoreTarget(null)
      setConfirmText('')
      openJobModal(job_id, '恢复进度')
    } catch (e: any) {
      message.error(String(e?.response?.data?.detail || e?.message || e))
    } finally {
      setRestoring(false)
    }
  }

  if (!canView) {
    return (
      <Card>
        <Alert type="warning" showIcon message="无权限"
          description="您没有「备份管理」的查看权限。请在「角色管理」中为您的角色授予 backup 权限。" />
      </Card>
    )
  }

  const columns: ColumnsType<BackupRecordRow> = [
    {
      title: '备份时间', dataIndex: 'created_at', width: 170,
      render: (v: string, r) => (
        <div>
          <div className="mono">{v || '-'}</div>
          <Text type="secondary" style={{ fontSize: 11 }}>{r.record_name}</Text>
        </div>
      ),
    },
    {
      title: '来源', dataIndex: 'source', width: 100,
      render: (v: string) => {
        const s = SOURCE_LABEL[v] || { text: v, color: 'default' }
        return <Tag color={s.color}>{s.text}</Tag>
      },
    },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (v: string, r) => (
        <Tooltip title={r.error_message || ''}>
          <Tag color={STATUS_LABEL[v]?.color}>{STATUS_LABEL[v]?.text || v}</Tag>
        </Tooltip>
      ),
    },
    {
      title: '大小（库 / 附件）', width: 200,
      render: (_, r) => (
        <span className="mono">{fmtSize(r.db_size)} / {fmtSize(r.uploads_size)}</span>
      ),
    },
    { title: '耗时', dataIndex: 'duration_seconds', width: 90, render: (v: number) => (v ? `${v}s` : '-') },
    {
      title: '校验和', width: 100,
      render: (_, r) => (
        <Tooltip title={`db: ${r.db_sha256 || '-'}\nuploads: ${r.uploads_sha256 || '-'}`}>
          <Button type="link" size="small" icon={<SafetyOutlined />}>sha256</Button>
        </Tooltip>
      ),
    },
    {
      title: '操作', width: 140, fixed: 'right',
      render: (_, r) => {
        const ok = r.status === 'success' && canManage
        return (
          <Space size={4}>
            <Tooltip title="下载库文件">
              <Button size="small" disabled={!ok} icon={<DatabaseOutlined />}
                onClick={() => downloadBackup(r.id, 'db', r.db_file)} />
            </Tooltip>
            <Tooltip title="下载附件包">
              <Button size="small" disabled={!ok} icon={<FileZipOutlined />}
                onClick={() => downloadBackup(r.id, 'uploads', r.uploads_file)} />
            </Tooltip>
            <Tooltip title="恢复">
              <Button size="small" danger disabled={!ok} icon={<RollbackOutlined />}
                onClick={() => { setRestoreTarget(r); setConfirmText('') }} />
            </Tooltip>
            <Tooltip title={r.id === latestId ? '最新一份备份不可删除' : '删除'}>
              <Popconfirm
                title="确认删除该备份？"
                disabled={!ok || r.id === latestId}
                onConfirm={async () => {
                  try { await backupApi.remove(r.id); message.success('已删除'); refresh() }
                  catch (e: any) { message.error(String(e?.response?.data?.detail || e?.message || e)) }
                }}
              >
                <Button size="small" danger disabled={!ok || r.id === latestId}
                  icon={<DeleteOutlined />} />
              </Popconfirm>
            </Tooltip>
          </Space>
        )
      },
    },
  ]

  // 进度弹窗派生状态：当前第几步、失败原因的通俗解释
  const typeLabel = job.type === 'restore' ? '恢复' : '备份'
  const stepDesc = STEP_DESC[job.type] || {}
  const activeIdx = job.steps.findIndex((s) => s.status === 'running' || s.status === 'fail')
  const currentStep = activeIdx >= 0 ? activeIdx
    : Math.min(job.steps.filter((s) => s.status === 'ok').length, Math.max(job.steps.length - 1, 0))
  const failInfo = job.status === 'fail'
    ? explainFailure([...job.logs].reverse().find((l) => l.level === 'ERR')?.msg || '未知原因，可展开下方技术日志查看')
    : null

  return (
    <Card className="backup-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div style={{ color: 'var(--text-secondary, #888)', fontSize: 12 }}>
          数据库 + 附件双文件备份；恢复将回滚到所选时间点（自动先打安全快照）。
          <Tooltip title={BACKUP_SCOPE_TIP}>
            <span style={{ marginLeft: 6, color: '#1677ff', cursor: 'help' }}>
              <QuestionCircleOutlined /> 备份范围
            </span>
          </Tooltip>
        </div>
        <Space>
          {stats?.next_run && <Text type="secondary" style={{ fontSize: 12 }}>下次定时：{stats.next_run}</Text>}
          <Button icon={<SettingOutlined />} disabled={!canManage} onClick={openConfig}>定时配置</Button>
          <Button type="primary" icon={<DatabaseOutlined />} disabled={!canManage}
            loading={false} onClick={runBackup}>立即备份</Button>
          <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>刷新</Button>
        </Space>
      </div>

      {stats && (
        <div style={{ display: 'flex', gap: 24, marginBottom: 12, fontSize: 12, color: '#888' }}>
          <span>成功备份 {stats.success_count} 份</span>
          <span>总占用 {fmtSize(stats.total_size)}</span>
          <span>磁盘剩余 {stats.disk_free_bytes ? fmtSize(stats.disk_free_bytes) : '-'}</span>
          <span>最近成功 {stats.latest_success_at || '-'}</span>
        </div>
      )}

      <Table<BackupRecordRow>
        rowKey="id"
        size="small"
        columns={columns}
        dataSource={rows}
        loading={loading}
        scroll={{ y: 'calc(100vh - 360px)' }}
        pagination={{
          current: page, pageSize, total, showSizeChanger: true,
          onChange: (p, ps) => { setPage(p); setPageSize(ps) },
        }}
      />

      <Modal
        open={jobOpen}
        title={jobTitle}
        width={720}
        footer={<Button onClick={closeJobModal}>关闭</Button>}
        onCancel={closeJobModal}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {job.steps.length === 0 ? (
            <Alert type="info" showIcon message="任务启动中…"
              description="正在从服务器获取进度，请稍候。" />
          ) : job.status === 'running' ? (
            <Alert type="info" showIcon
              message={`正在${typeLabel}：第 ${currentStep + 1} 步 / 共 ${job.steps.length} 步 · ${job.steps[currentStep]?.name || ''}`}
              description={`已进行 ${fmtElapsed(Date.now() - jobStartRef.current)}。任务在服务器后台执行，关闭本窗口不会中断。`} />
          ) : job.status === 'ok' ? (
            <Alert type="success" showIcon message={`${typeLabel}成功`}
              description={job.type === 'restore'
                ? '系统已恢复正常访问，建议刷新页面重新加载数据。'
                : `已生成备份${job.result?.record_name ? `（编号 ${job.result.record_name}）` : ''}，可在列表中查看、下载或用于恢复。`} />
          ) : (
            <Alert type="error" showIcon message={`${typeLabel}失败`}
              description={
                <div>
                  <div>{failInfo?.summary}</div>
                  {failInfo?.detail && (
                    <Text type="secondary" style={{ fontSize: 12, wordBreak: 'break-all' }}>
                      原始信息：{failInfo.detail}
                    </Text>
                  )}
                </div>
              } />
          )}

          <Steps
            direction="vertical"
            size="small"
            current={currentStep}
            items={job.steps.map((s) => ({
              title: s.name,
              description: stepDesc[s.name],
              status: STEP_STATUS_MAP[s.status] || 'wait',
              icon: s.status === 'running' ? <LoadingOutlined /> : undefined,
            }))}
          />

          <Collapse
            ghost
            size="small"
            activeKey={logOpenKeys}
            onChange={(keys) => setLogOpenKeys(Array.isArray(keys) ? keys : [keys])}
            items={[{
              key: 'logs',
              label: '技术日志（排查问题时展开，可提供给系统管理员）',
              children: (
                <div ref={logBoxRef} style={{
                  maxHeight: 320, overflow: 'auto', background: '#0b1021', color: '#c9d1e3',
                  borderRadius: 6, padding: 8, fontSize: 12, fontFamily: 'Consolas, monospace',
                }}>
                  {job.logs.length === 0 ? <div>等待日志…</div> : job.logs.map((l, i) => (
                    <div key={i}>
                      <span style={{ color: '#6e7a9a' }}>[{l.ts}]</span>{' '}
                      <span style={{ color: l.level === 'OK' ? '#52c41a' : l.level === 'ERR' ? '#ff4d4f' : undefined }}>
                        {l.msg}
                      </span>
                    </div>
                  ))}
                </div>
              ),
            }]}
          />
        </Space>
      </Modal>

      <Modal
        open={!!restoreTarget}
        title="恢复确认"
        okText="开始恢复"
        okButtonProps={{ danger: true, disabled: confirmText.trim() !== '确认恢复', loading: restoring }}
        onOk={submitRestore}
        onCancel={() => { setRestoreTarget(null); setConfirmText('') }}
      >
        <Alert
          type="warning" showIcon style={{ marginBottom: 12 }}
          message={`将恢复到 ${restoreTarget?.created_at || ''}`}
          description={
            <ul style={{ paddingLeft: 18, margin: 0 }}>
              <li>恢复期间系统进入维护模式，所有业务请求暂停（预计数分钟）</li>
              <li>所选时间点之后产生的数据将丢失</li>
              <li>系统会自动先打一份「恢复前快照」用于回退</li>
            </ul>
          }
        />
        <div style={{ marginBottom: 8 }}>请输入「<b>确认恢复</b>」以确认：</div>
        <Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)}
          placeholder="确认恢复" />
      </Modal>

      <Modal
        open={configOpen}
        title="定时备份配置"
        okText="保存"
        confirmLoading={savingConfig}
        onOk={saveConfig}
        onCancel={() => setConfigOpen(false)}
      >
        {config && (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span>启用定时备份：</span>
              <Switch checked={config.enabled} onChange={(v) => setConfig({ ...config, enabled: v })} />
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span>频率：</span>
              <Select value={config.frequency} style={{ width: 120 }}
                onChange={(v) => setConfig({ ...config, frequency: v })}
                options={[{ value: 'daily', label: '每天' }, { value: 'weekly', label: '每周' }]} />
              {config.frequency === 'weekly' && (
                <Select value={config.weekday} style={{ width: 100 }}
                  onChange={(v) => setConfig({ ...config, weekday: v })}
                  options={[1, 2, 3, 4, 5, 6, 7].map((d) => ({ value: d, label: `周${'一二三四五六日'[d - 1]}` }))} />
              )}
              <Input value={config.schedule_time} style={{ width: 90 }} placeholder="HH:MM"
                onChange={(e) => setConfig({ ...config, schedule_time: e.target.value })} />
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span>保留份数：</span>
              <Input type="number" min={1} max={100} value={config.retention_count}
                style={{ width: 90 }}
                onChange={(e) => setConfig({ ...config, retention_count: Number(e.target.value) || 7 })} />
              <Text type="secondary" style={{ fontSize: 12 }}>最新一份永不删除</Text>
            </div>
          </Space>
        )}
      </Modal>
    </Card>
  )
}
