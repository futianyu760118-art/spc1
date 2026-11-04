import React, { useCallback, useEffect, useState } from 'react'
import {
  Button, Drawer, Empty, Input, Modal, Popconfirm, Select, Space, Switch, Table, Tag, Typography, Upload, message,
} from 'antd'
import { InboxOutlined, ReloadOutlined } from '@ant-design/icons'
import { agentApi, AgentSkill, AgentSkillFile } from '../../../services/agent'
import Markdown from '../../../components/Markdown'

const { Text } = Typography
const PAGE_SIZE = 8

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'active', label: '启用' },
  { value: 'disabled', label: '停用' },
]

const SOURCE_OPTIONS = [
  { value: '', label: '全部来源' },
  { value: 'builtin', label: '内置' },
  { value: 'imported', label: '导入' },
]

const FILE_KIND_LABELS: Record<string, string> = {
  skill: 'SKILL.md',
  script: '脚本',
  reference: '参考文档',
  asset: '资源',
  file: '文件',
}

function formatSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

export default function SkillLibraryTab() {
  const [skills, setSkills] = useState<AgentSkill[]>([])
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState('')
  const [source, setSource] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [importOpen, setImportOpen] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importing, setImporting] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [detail, setDetail] = useState<AgentSkill | null>(null)
  const [filePreview, setFilePreview] = useState<{ path: string; content: string; size: number } | null>(null)
  const [fileLoading, setFileLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await agentApi.adminSkills({
        keyword, status, source, page, page_size: PAGE_SIZE,
      })
      setSkills(res.data?.items || [])
      setTotal(res.data?.total || 0)
    } finally {
      setLoading(false)
    }
  }, [keyword, status, source, page])

  useEffect(() => { load() }, [load])

  const openPreview = async (row: AgentSkill) => {
    const res: any = await agentApi.adminSkill(row.id)
    setDetail(res.data)
    setFilePreview(null)
    setPreviewOpen(true)
  }

  const previewFile = async (file: AgentSkillFile) => {
    if (!detail) return
    if (file.kind === 'skill') {
      setFilePreview({ path: file.path, content: detail.instructions || '', size: file.size })
      return
    }
    setFileLoading(true)
    try {
      const res: any = await agentApi.adminSkillFile(detail.id, file.path)
      setFilePreview(res.data)
    } finally {
      setFileLoading(false)
    }
  }

  const toggleStatus = async (row: AgentSkill, checked: boolean) => {
    await agentApi.updateSkillStatus(row.id, checked ? 'active' : 'disabled')
    message.success(checked ? '已启用' : '已停用')
    await load()
  }

  const remove = async (row: AgentSkill) => {
    const res: any = await agentApi.deleteSkill(row.id)
    message.success(`已删除技能 ${res.data?.name || row.name}`)
    await load()
  }

  const sync = async () => {
    const res: any = await agentApi.syncSkills()
    const errors: string[] = res.data?.errors || []
    message.success(`已同步 ${res.data?.synced || 0} 个技能，移除 ${res.data?.removed || 0} 个`)
    if (errors.length) {
      Modal.warning({
        title: '部分技能未同步',
        content: <div style={{ maxHeight: 240, overflow: 'auto' }}>{errors.map((item, i) => <div key={i}>{item}</div>)}</div>,
      })
    }
    await load()
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
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="ai-card">
      <div className="ai-card-head">
        <h3>技能库</h3>
        <span className="ai-hint">技能以磁盘文件夹为准，SKILL.md 定义能力说明</span>
      </div>

      <div className="ai-toolbar">
        <Input.Search
          placeholder="名称 / 文件夹 / 说明" allowClear style={{ width: 260 }}
          onSearch={value => { setKeyword(value); setPage(1) }}
        />
        <Select
          value={source} style={{ width: 130 }}
          onChange={value => { setSource(value); setPage(1) }}
          options={SOURCE_OPTIONS}
        />
        <Select
          value={status} style={{ width: 130 }}
          onChange={value => { setStatus(value); setPage(1) }}
          options={STATUS_OPTIONS}
        />
        <Button icon={<ReloadOutlined />} onClick={sync}>同步技能目录</Button>
        <Button type="primary" onClick={() => { setImportFile(null); setImportOpen(true) }}>导入技能 zip</Button>
        <span className="ai-toolbar-meta">共 {total} 个</span>
      </div>

      <Table
        size="small" rowKey="id" loading={loading} dataSource={skills} tableLayout="fixed"
        scroll={{ x: 980 }}
        pagination={{
          current: page, pageSize: PAGE_SIZE, total, size: 'small', showSizeChanger: false,
          onChange: setPage,
        }}
        columns={[
          { title: '名称', dataIndex: 'name', width: 150, ellipsis: true },
          { title: '文件夹', dataIndex: 'skill_key', width: 140, ellipsis: true },
          { title: '说明', dataIndex: 'description', ellipsis: true },
          {
            title: '来源', dataIndex: 'source', width: 76,
            render: (value: string) => (
              <Tag color={value === 'imported' ? 'blue' : 'default'}>
                {value === 'imported' ? '导入' : '内置'}
              </Tag>
            ),
          },
          { title: '文件数', dataIndex: 'file_count', width: 70 },
          {
            title: '执行器', dataIndex: 'executor_name', width: 140, ellipsis: true,
            render: (value: string | null, row: AgentSkill) => value
              ? <Tag color={row.executor_available ? 'purple' : 'red'}>{value}</Tag>
              : <Text type="secondary">-</Text>,
          },
          {
            title: '状态', dataIndex: 'status', width: 76,
            render: (value: string, row: AgentSkill) => (
              <Switch size="small" checked={value === 'active'} onChange={checked => toggleStatus(row, checked)} />
            ),
          },
          { title: '绑定智能体', dataIndex: 'bound_agents_count', width: 90 },
          {
            title: '操作', width: 110,
            render: (_: any, row: AgentSkill) => (
              <Space size={0}>
                <Button type="link" size="small" onClick={() => openPreview(row)}>预览</Button>
                {row.source === 'imported' && (
                  <Popconfirm
                    title="删除该技能？"
                    description="会删除磁盘文件夹并解绑所有智能体。"
                    okText="删除" cancelText="取消" okButtonProps={{ danger: true }}
                    onConfirm={() => remove(row)}
                  >
                    <Button type="link" size="small" danger>删除</Button>
                  </Popconfirm>
                )}
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title="导入技能 zip"
        open={importOpen}
        onCancel={() => setImportOpen(false)}
        onOk={doImport}
        confirmLoading={importing}
        okText="导入"
        destroyOnClose
        className="sc-page"
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

      <Drawer
        title={detail ? `技能预览 · ${detail.name}` : '技能预览'}
        width={720}
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        className="sc-page"
      >
        {detail ? (
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <Space wrap>
              <Tag>{detail.skill_key}</Tag>
              <Tag color={detail.source === 'imported' ? 'blue' : 'default'}>
                {detail.source === 'imported' ? '导入' : '内置'}
              </Tag>
              {detail.executor_name && (
                <Tag color={detail.executor_available ? 'purple' : 'red'}>
                  执行器：{detail.executor_name}{detail.executor_available ? '' : '（不可用）'}
                </Tag>
              )}
              <Tag color={detail.status === 'active' ? 'green' : 'default'}>
                {detail.status === 'active' ? '启用' : '停用'}
              </Tag>
              <Tag color={detail.script_execution_available ? 'green' : 'default'}>
                脚本执行：{detail.script_execution_available ? '已启用' : '未启用'}
              </Tag>
            </Space>
            <Text type="secondary">{detail.description}</Text>
            <div>
              <Text strong>文件</Text>
              <Table
                size="small" rowKey="path" pagination={false} dataSource={detail.files || []}
                style={{ marginTop: 6 }}
                onRow={file => ({ onClick: () => previewFile(file), style: { cursor: 'pointer' } })}
                columns={[
                  { title: '路径', dataIndex: 'path', ellipsis: true },
                  {
                    title: '类型', dataIndex: 'kind', width: 90,
                    render: (value: string) => FILE_KIND_LABELS[value] || value,
                  },
                  { title: '大小', dataIndex: 'size', width: 90, render: formatSize },
                ]}
              />
            </div>
            {filePreview && (
              <div>
                <Space>
                  <Text strong>文件内容：{filePreview.path}</Text>
                  <Text type="secondary">{formatSize(filePreview.size)}</Text>
                </Space>
                <pre style={{
                  marginTop: 6, maxHeight: 320, overflow: 'auto', background: '#f8fafc',
                  border: '1px solid #e2e8f0', borderRadius: 8, padding: 12, fontSize: 12,
                }}>
                  {filePreview.content}
                </pre>
              </div>
            )}
            {fileLoading && <Text type="secondary">正在读取文件...</Text>}
            <div>
              <Text strong>SKILL.md</Text>
              <div style={{
                marginTop: 6, maxHeight: 360, overflow: 'auto', border: '1px solid #e2e8f0',
                borderRadius: 8, padding: 12,
              }}>
                <Markdown>{detail.instructions || ''}</Markdown>
              </div>
            </div>
            <Text type="secondary" className="ai-muted">
              {detail.script_execution_available
                ? '脚本可在隔离沙箱中执行；参数通过 stdin JSON 传入。'
                : '脚本执行未启用（未配置沙箱）；只能读取文本资源。'}
            </Text>
          </Space>
        ) : <Empty />}
      </Drawer>
    </div>
  )
}
