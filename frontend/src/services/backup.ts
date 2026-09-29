import api from './api'
import { useAuthStore } from '../store/auth'

export interface BackupRecordRow {
  id: number
  record_name: string
  db_file: string
  uploads_file: string
  db_size: number
  uploads_size: number
  db_sha256: string | null
  uploads_sha256: string | null
  source: 'manual' | 'scheduled' | 'safety'
  status: 'running' | 'success' | 'failed' | 'deleted'
  duration_seconds: number
  error_message: string | null
  created_by: number | null
  created_at: string
}

export interface BackupConfigVo {
  enabled: boolean
  frequency: 'daily' | 'weekly'
  schedule_time: string
  weekday: number
  retention_count: number
}

export interface BackupJobVo {
  job_id: string
  type: 'backup' | 'restore'
  status: 'running' | 'ok' | 'fail'
  steps: { name: string; status: string }[]
  logs: { ts: string; level: string; msg: string }[]
  result: any
}

export interface BackupStats {
  success_count: number
  total_size: number
  latest_success_at: string | null
  next_run: string | null
  disk_free_bytes: number | null
  backup_dir: string
}

async function unwrap<T>(p: Promise<any>): Promise<T> {
  const r: any = await p
  return (r?.data ?? r) as T
}

export const backupApi = {
  list: (params: { page: number; page_size: number }) =>
    unwrap<{ items: BackupRecordRow[]; total: number; page: number; page_size: number; stats: BackupStats }>(
      api.get('/system/backups/records', { params })),
  run: () => unwrap<{ job_id: string }>(api.post('/system/backups/run')),
  restore: (id: number, confirm_text: string) =>
    unwrap<{ job_id: string }>(api.post(`/system/backups/records/${id}/restore`, { confirm_text })),
  remove: (id: number) => unwrap<any>(api.delete(`/system/backups/records/${id}`)),
  config: () => unwrap<BackupConfigVo>(api.get('/system/backups/config')),
  saveConfig: (cfg: BackupConfigVo) => unwrap<BackupConfigVo>(api.put('/system/backups/config', cfg)),
  job: (jobId: string) => unwrap<BackupJobVo>(api.get(`/system/backups/jobs/${encodeURIComponent(jobId)}`)),
}

/** 备份文件下载：fetch + Bearer header（blob 不走 axios 拦截器，同 SSE 惯例） */
export async function downloadBackup(id: number, type: 'db' | 'uploads', fileName: string) {
  const token = useAuthStore.getState().currentToken || ''
  const res = await fetch(`/api/v1/system/backups/records/${id}/download?type=${type}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`下载失败 HTTP ${res.status}`)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  a.click()
  URL.revokeObjectURL(url)
}
