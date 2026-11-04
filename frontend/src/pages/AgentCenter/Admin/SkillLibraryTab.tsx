import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Empty, Modal, Popconfirm, Spin, Upload, message,
} from 'antd'
import {
  DeleteOutlined, FileTextOutlined, FolderOutlined, InboxOutlined,
  ReloadOutlined, SearchOutlined, UploadOutlined,
} from '@ant-design/icons'
import { agentApi, AgentSkill, AgentSkillFile } from '../../../services/agent'

const SOURCE_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'builtin', label: '内置' },
  { value: 'imported', label: '导入' },
]

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'active', label: '启用' },
  { value: 'disabled', label: '停用' },
]

const FILE_KIND_LABELS: Record<string, string> = {
  skill: 'md',
  script: 'py',
  reference: 'md',
  asset: 'asset',
  file: 'file',
}

interface Summary {
  active: number
  disabled: number
  executors: number
  total: number
}

interface Props {
  canManage: boolean
  onOpenAgents: () => void
  onChanged: () => void
}

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function sourceLabel(skill: AgentSkill): string {
  return skill.source === 'imported' ? '导入' : '内置'
}

export default function SkillLibraryTab({ canManage, onOpenAgents, onChanged }: Props) {
  const [skills, setSkills] = useState<AgentSkill[]>([])
  const [total, setTotal] = useState(0)
  const [summary, setSummary] = useState<Summary>({ active: 0, disabled: 0, executors: 0, total: 0 })
  const [loading, setLoading] = useState(false)
  const [keywordInput, setKeywordInput] = useState('')
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState('')
  const [source, setSource] = useState('')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<AgentSkill | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [activeFile, setActiveFile] = useState('')
  const [preview, setPreview] = useState<{ path: string; content: string; size: number } | null>(null)
  const [fileLoading, setFileLoading] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importing, setImporting] = useState(false)

  const loadSummary = useCallback(async () => {
    try {
      const res: any = await agentApi.adminSkills({ page: 1, page_size: 100 })
      const items: AgentSkill[] = res.data?.items || []
      setSummary({
        active: items.filter(item => item.status === 'active').length,
        disabled: items.filter(item => item.status !== 'active').length,
        executors: items.filter(item => Boolean(item.executor_name)).length,
        total: Number(res.data?.total || items.length),
      })
    } catch {
      // 汇总信息失败不影响主列表
    }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await agentApi.adminSkills({
        keyword, status, source, page: 1, page_size: 100,
      })
      const items: AgentSkill[] = res.data?.items || []
      setSkills(items)
      setTotal(Number(res.data?.total || 0))
      setSelectedId(current => (
        items.some(item => item.id === current) ? current : (items[0]?.id ?? null)
      ))
    } finally {
      setLoading(false)
    }
  }, [keyword, status, source])

  useEffect(() => { load() }, [load])
  useEffect(() => { loadSummary() }, [loadSummary])

  useEffect(() => {
    const timer = setTimeout(() => {
      setKeyword(keywordInput.trim())
    }, 250)
    return () => clearTimeout(timer)
  }, [keywordInput])

  const readFile = useCallback(async (skill: AgentSkill, file: AgentSkillFile) => {
    setActiveFile(file.path)
    setFileLoading(true)
    try {
      if (file.kind === 'skill') {
        setPreview({
          path: file.path,
          content: skill.instructions || '',
          size: file.size,
        })
        return
      }
      const res: any = await agentApi.adminSkillFile(skill.id, file.path)
      setPreview(res.data)
    } finally {
      setFileLoading(false)
    }
  }, [])

  const openSkill = useCallback(async (skillId: number) => {
    setDetailLoading(true)
    setDetail(null)
    setPreview(null)
    setActiveFile('')
    try {
      const res: any = await agentApi.adminSkill(skillId)
      const data: AgentSkill = res.data
      setDetail(data)
      const files = data.files || []
      const first = files.find(file => file.kind === 'skill') || files[0]
      if (first) {
        await readFile(data, first)
      } else {
        setActiveFile('')
        setPreview(null)
      }
    } finally {
      setDetailLoading(false)
    }
  }, [readFile])

  useEffect(() => {
    if (selectedId == null) {
      setDetail(null)
      setPreview(null)
      setActiveFile('')
      return
    }
    openSkill(selectedId)
  }, [selectedId, openSkill])

  const selectedRow = useMemo(
    () => skills.find(item => item.id === selectedId) || null,
    [skills, selectedId],
  )

  const toggleStatus = async (skill: AgentSkill) => {
    const next = skill.status === 'active' ? 'disabled' : 'active'
    await agentApi.updateSkillStatus(skill.id, next)
    message.success(next === 'active' ? '已启用' : '已停用')
    setSkills(current => current.map(item => (
      item.id === skill.id ? { ...item, status: next } : item
    )))
    setDetail(current => (current && current.id === skill.id ? { ...current, status: next } : current))
    await loadSummary()
  }

  const remove = async (skill: AgentSkill) => {
    const res: any = await agentApi.deleteSkill(skill.id)
    message.success(`已删除技能 ${res.data?.name || skill.name}`)
    await load()
    await loadSummary()
    onChanged()
  }

  const sync = async () => {
    const res: any = await agentApi.syncSkills()
    const errors: string[] = res.data?.errors || []
    message.success(`已同步 ${res.data?.synced || 0} 个技能，移除 ${res.data?.removed || 0} 个`)
    if (errors.length) {
      Modal.warning({
        title: '部分技能未同步',
        content: (
          <div style={{ maxHeight: 240, overflow: 'auto' }}>
            {errors.map((item, index) => <div key={index}>{item}</div>)}
          </div>
        ),
      })
    }
    await load()
    await loadSummary()
    onChanged()
  }

  const doImport = async () => {
    if (!importFile) {
      message.warning('请选择 zip 技能包')
      return
    }
    setImporting(true)
    try {
      const res: any = await agentApi.importSkill(importFile)
      message.success(`已导入技能 ${res.data?.name || ''}`)
      setImportOpen(false)
      setImportFile(null)
      await load()
      await loadSummary()
      onChanged()
      if (res.data?.id) setSelectedId(Number(res.data.id))
    } finally {
      setImporting(false)
    }
  }

  const detailFiles = detail?.files || []
  const title = detail?.name || selectedRow?.name || '技能详情'

  return (
    <div className="ac-skill-workbench">
      <aside className="ac-surface ac-skill-index" aria-label="技能库">
        <div className="ac-index-toolbar">
          <label className="ac-search">
            <SearchOutlined />
            <input
              value={keywordInput}
              placeholder="名称 / 文件夹 / 说明"
              onChange={event => setKeywordInput(event.target.value)}
            />
          </label>
          <div className="ac-chips">
            {SOURCE_OPTIONS.map(option => (
              <button
                key={option.value}
                type="button"
                className={`ac-chip ${source === option.value ? 'active' : ''}`}
                onClick={() => setSource(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className="ac-chips" style={{ marginTop: 4 }}>
            {STATUS_OPTIONS.map(option => (
              <button
                key={option.value}
                type="button"
                className={`ac-chip ${status === option.value ? 'active' : ''}`}
                onClick={() => setStatus(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <div className="ac-skill-summary">
          <span><b>{summary.active}</b> 启用</span>
          <span><b>{summary.disabled}</b> 停用</span>
          <span><b>{summary.executors}</b> 执行器</span>
          <span style={{ marginLeft: 'auto' }}><b>SKILL.md</b> 为准</span>
        </div>

        {loading && skills.length === 0 ? (
          <div className="ac-empty"><Spin /></div>
        ) : skills.length === 0 ? (
          <div className="ac-empty">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的技能" />
          </div>
        ) : (
          <ul className="ac-skill-list">
            {skills.map(skill => (
              <li
                key={skill.id}
                role="button"
                tabIndex={0}
                className={`ac-skill-row ${skill.id === selectedId ? 'active' : ''}`}
                onClick={() => setSelectedId(skill.id)}
                onKeyDown={event => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    setSelectedId(skill.id)
                  }
                }}
              >
                <span className="ac-skill-ico">SK</span>
                <span className="ac-skill-row-main">
                  <span className="ac-skill-row-name">
                    <span className="name">{skill.name}</span>
                  </span>
                  <span className="ac-skill-row-meta">
                    <span className={`ac-mini-badge ${skill.source === 'imported' ? 'imported' : ''}`}>
                      {sourceLabel(skill)}
                    </span>
                    {skill.executor_name && <span className="ac-mini-badge exec">可执行</span>}
                    <span>{skill.file_count ?? (skill.files || []).length} 文件 · 绑定 {skill.bound_agents_count || 0}</span>
                  </span>
                </span>
                {canManage ? (
                  <button
                    type="button"
                    className={`ac-switch ${skill.status === 'active' ? 'on' : ''}`}
                    aria-pressed={skill.status === 'active'}
                    aria-label={skill.status === 'active' ? '停用技能' : '启用技能'}
                    onClick={event => { event.stopPropagation(); toggleStatus(skill) }}
                  />
                ) : (
                  <span className={`ac-status ${skill.status === 'active' ? '' : 'off'}`}>
                    {skill.status === 'active' ? '启用' : '停用'}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}

        <div className="ac-index-foot">
          <span>共 {total} 个技能</span>
          {canManage && (
            <>
              <button type="button" className="ac-link" onClick={sync}>
                <ReloadOutlined /> 同步目录
              </button>
              <button type="button" className="ac-link" onClick={() => { setImportFile(null); setImportOpen(true) }}>
                <UploadOutlined /> 导入 zip
              </button>
            </>
          )}
        </div>
      </aside>

      <section className="ac-surface ac-skill-sheet" aria-live="polite">
        {detailLoading && !detail ? (
          <div className="ac-empty" style={{ paddingTop: 100 }}><Spin /></div>
        ) : !detail ? (
          <div className="ac-empty" style={{ paddingTop: 100 }}>
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择一个技能查看详情" />
          </div>
        ) : (
          <>
            <div className="ac-skill-sheet-head">
              <span className="ac-skill-ico">SK</span>
              <div className="ac-skill-sheet-title">
                <div className="key">技能 · {detail.skill_key || `skill-${detail.id}`}</div>
                <h2>
                  {title}
                  <span className={`ac-status ${detail.status === 'active' ? '' : 'off'}`}>
                    {detail.status === 'active' ? '启用' : '停用'}
                  </span>
                </h2>
                <p>{detail.description || '暂无说明'}</p>
              </div>
              <div className="ac-skill-sheet-actions">
                {canManage && (
                  <button type="button" className="ac-btn" onClick={onOpenAgents}>
                    去智能体绑定
                  </button>
                )}
                {canManage && detail.source === 'imported' && (
                  <Popconfirm
                    title="删除该技能？"
                    description="会删除磁盘文件夹并解绑所有智能体。"
                    okText="删除"
                    cancelText="取消"
                    okButtonProps={{ danger: true }}
                    onConfirm={() => remove(detail)}
                  >
                    <button type="button" className="ac-btn" style={{ color: 'var(--ac-danger)' }}>
                      <DeleteOutlined /> 删除
                    </button>
                  </Popconfirm>
                )}
              </div>
            </div>

            <div className="ac-skill-meta">
              <div>
                <span>文件夹</span>
                <b className="mono">
                  {detail.source === 'imported' ? 'skills-imported' : 'skills'}/{detail.skill_key || `skill-${detail.id}`}
                </b>
              </div>
              <div><span>来源</span><b>{sourceLabel(detail)}</b></div>
              <div><span>文件</span><b>{detail.file_count ?? detailFiles.length} 个</b></div>
              <div><span>执行器</span><b>{detail.executor_name || '—'}</b></div>
              <div><span>绑定智能体</span><b>{detail.bound_agents_count || 0} 个</b></div>
              <div><span>脚本执行</span><b>{detail.script_execution_available ? '已启用' : '未启用'}</b></div>
            </div>

            <div className="ac-file-grid">
              <div className="ac-file-tree">
                <div className="ac-file-tree-title">文件树</div>
                {detailFiles.map(file => (
                  <div
                    key={file.path}
                    className={`ac-file-row ${activeFile === file.path ? 'active' : ''}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => readFile(detail, file)}
                    onKeyDown={event => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        readFile(detail, file)
                      }
                    }}
                  >
                    {file.path.includes('/') ? <FolderOutlined /> : <FileTextOutlined />}
                    <span>{file.path}</span>
                    <span className="kind">
                      {file.path.split('.').pop() || FILE_KIND_LABELS[file.kind] || file.kind}
                    </span>
                  </div>
                ))}
                {detailFiles.length === 0 && (
                  <div className="ac-empty">暂无文件</div>
                )}
              </div>
              <div className="ac-file-preview">
                <div className="ac-file-preview-head">
                  <span>{preview?.path || 'SKILL.md'}</span>
                  <span className="ro">只读</span>
                  {preview && <span style={{ marginLeft: 'auto' }}>{formatSize(preview.size)}</span>}
                </div>
                {fileLoading ? (
                  <div className="ac-empty"><Spin size="small" /></div>
                ) : (
                  <pre>{preview?.content || '选择左侧文件查看内容'}</pre>
                )}
              </div>
            </div>
          </>
        )}
      </section>

      <Modal
        title="导入技能 zip"
        open={importOpen}
        onCancel={() => setImportOpen(false)}
        onOk={doImport}
        confirmLoading={importing}
        okText="导入"
        destroyOnClose
        className="sc-page ai-center"
      >
        <Upload.Dragger
          accept=".zip"
          maxCount={1}
          beforeUpload={file => { setImportFile(file); return false }}
          onRemove={() => setImportFile(null)}
          fileList={importFile ? [{ uid: '-1', name: importFile.name, status: 'done' }] : []}
        >
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">点击或拖拽 zip 技能包</p>
          <p className="ant-upload-hint">zip 内应为一个技能文件夹（含 SKILL.md），或根目录直接包含 SKILL.md</p>
        </Upload.Dragger>
      </Modal>
    </div>
  )
}
