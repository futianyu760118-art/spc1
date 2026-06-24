import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Table, Button, Modal, Form, Input, Select, Space, message,
  Popconfirm, Tag, Switch, Tabs, Card, Statistic, Row, Col, DatePicker,
  Typography, Tooltip, Alert, InputNumber, Badge, Empty,
} from 'antd'
import {
  PlusOutlined, CopyOutlined, ApiOutlined,
  DatabaseOutlined, BarChartOutlined, KeyOutlined, ReloadOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined,
  SearchOutlined, SettingOutlined, SafetyCertificateOutlined,
  ExclamationCircleOutlined, BookOutlined, DownloadOutlined,
} from '@ant-design/icons'
import { dataSupplyApi } from '../../../services/api'
import dayjs from 'dayjs'

const { Text } = Typography
const { RangePicker } = DatePicker

// 兼容 HTTP 环境的复制函数
const copyToClipboard = (text: string) => {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => message.success('已复制'))
  } else {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    message.success('已复制')
  }
}

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */
interface DataTypeOption {
  value: string
  label: string
}

interface ConfigItem {
  id: number
  data_type: string
  data_name: string
  description: string | null
  model_name: string
  allowed_fields_json: string | null
  filter_fields_json: string | null
  is_active: boolean
  created_at: string | null
  updated_at: string | null
}

interface ApiKeyItem {
  id: number
  key_name: string
  api_key: string
  app_key: string | null
  description: string | null
  is_active: boolean
  allowed_data_types_json: string | null
  rate_limit: number
  expires_at: string | null
  ip_whitelist_json: string | null
  created_by: string | null
  created_at: string | null
  updated_at: string | null
}

interface CallLogItem {
  id: number
  api_key_id: number | null
  api_key_name: string | null
  data_type: string
  request_params_json: string | null
  response_status: number | null
  response_count: number
  ip_address: string | null
  user_agent: string | null
  duration_ms: number | null
  called_at: string | null
}

interface AvailableType {
  data_type: string
  data_name: string
  description: string
  model_name: string
  exposed_fields: string[]
  default_fields: string[]
  is_configured: boolean
  is_active: boolean
  allowed_fields: string[]
  filter_fields: string[]
  mask_fields: string[]
  search_fields: string[]
}

interface Statistics {
  value: string
  label: string
}

interface Statistics {
  total_calls: number
  success_calls: number
  failed_calls: number
  avg_duration_ms: number | null
  by_data_type: Record<string, number>
  by_date: Record<string, number>
  by_api_key: Record<string, number>
}

export default function DataSupply() {
  const [activeTab, setActiveTab] = useState('configs')
  const [loading, setLoading] = useState(false)

  // ── 动态数据类型选项（替代硬编码） ──
  const [dataTypeOptions, setDataTypeOptions] = useState<DataTypeOption[]>([])

  // 从 API 获取的选项构建 label 映射
  const dataTypeLabelMap = useMemo(
    () => Object.fromEntries(dataTypeOptions.map(o => [o.value, o.label])),
    [dataTypeOptions]
  )

  // ── 配置 ──
  const [availableTypes, setAvailableTypes] = useState<AvailableType[]>([])
  const [configs, setConfigs] = useState<ConfigItem[]>([])
  const [configTotal, setConfigTotal] = useState(0)
  const [configPage, setConfigPage] = useState(1)
  const [configModalOpen, setConfigModalOpen] = useState(false)
  const [editingConfig, setEditingConfig] = useState<ConfigItem | null>(null)
  const [configForm] = Form.useForm()
  const [configSearchText, setConfigSearchText] = useState('')

  // ── API Key ──
  const [apiKeys, setApiKeys] = useState<ApiKeyItem[]>([])
  const [apiKeyTotal, setApiKeyTotal] = useState(0)
  const [apiKeyPage, setApiKeyPage] = useState(1)
  const [apiKeyModalOpen, setApiKeyModalOpen] = useState(false)
  const [editingApiKey, setEditingApiKey] = useState<ApiKeyItem | null>(null)
  const [apiKeyForm] = Form.useForm()
  const [newKeyVisible, setNewKeyVisible] = useState<string | null>(null)
  const [newKeyInfo, setNewKeyInfo] = useState<{ app_key: string; app_secret: string } | null>(null)

  // ── 调用日志 ──
  const [callLogs, setCallLogs] = useState<CallLogItem[]>([])
  const [callLogTotal, setCallLogTotal] = useState(0)
  const [callLogPage, setCallLogPage] = useState(1)
  const [logFilters, setLogFilters] = useState<{ data_type?: string; dateRange?: any }>({})

  // ── 统计 ──
  const [statistics, setStatistics] = useState<Statistics | null>(null)

  // ═══════════════════════════════════════════
  // 数据加载
  // ═══════════════════════════════════════════

  const fetchDataTypeOptions = useCallback(async () => {
    try {
      const res: any = await dataSupplyApi.dataTypeOptions()
      setDataTypeOptions(res.data || [])
    } catch { /* silent */ }
  }, [])

  const fetchAvailableTypes = useCallback(async () => {
    try {
      const res: any = await dataSupplyApi.listAvailableTypes()
      setAvailableTypes(res.data || [])
    } catch { /* silent */ }
  }, [])

  const fetchConfigs = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await dataSupplyApi.listConfigs({ page: configPage, page_size: 20 })
      setConfigs(res.data?.items || [])
      setConfigTotal(res.data?.total || 0)
    } catch { message.error('加载配置失败') }
    setLoading(false)
  }, [configPage])

  const fetchApiKeys = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await dataSupplyApi.listApiKeys({ page: apiKeyPage, page_size: 20 })
      setApiKeys(res.data?.items || [])
      setApiKeyTotal(res.data?.total || 0)
    } catch { message.error('加载 API Key 失败') }
    setLoading(false)
  }, [apiKeyPage])

  const fetchCallLogs = useCallback(async () => {
    setLoading(true)
    try {
      const params: any = { page: callLogPage, page_size: 20 }
      if (logFilters.data_type) params.data_type = logFilters.data_type
      if (logFilters.dateRange) {
        params.start_date = logFilters.dateRange[0].format('YYYY-MM-DD')
        params.end_date = logFilters.dateRange[1].format('YYYY-MM-DD')
      }
      const res: any = await dataSupplyApi.listCallLogs(params)
      setCallLogs(res.data?.items || [])
      setCallLogTotal(res.data?.total || 0)
    } catch { message.error('加载调用日志失败') }
    setLoading(false)
  }, [callLogPage, logFilters])

  const fetchStatistics = useCallback(async () => {
    try {
      const params: any = {}
      if (logFilters.data_type) params.data_type = logFilters.data_type
      if (logFilters.dateRange) {
        params.start_date = logFilters.dateRange[0].format('YYYY-MM-DD')
        params.end_date = logFilters.dateRange[1].format('YYYY-MM-DD')
      }
      const res: any = await dataSupplyApi.getStatistics(params)
      setStatistics(res.data || null)
    } catch { /* silent */ }
  }, [logFilters])

  useEffect(() => {
    // 首次加载时获取动态选项
    fetchDataTypeOptions()
  }, [fetchDataTypeOptions])

  useEffect(() => {
    if (activeTab === 'configs') {
      fetchAvailableTypes()
      fetchConfigs()
    } else if (activeTab === 'api-keys') {
      fetchApiKeys()
      // 切换到 API Key tab 时刷新选项
      fetchDataTypeOptions()
    } else if (activeTab === 'call-logs') {
      fetchCallLogs()
      fetchStatistics()
    }
  }, [activeTab, fetchConfigs, fetchApiKeys, fetchCallLogs, fetchAvailableTypes, fetchStatistics, fetchDataTypeOptions])

  // ═══════════════════════════════════════════
  // 配置操作
  // ═══════════════════════════════════════════

  const handleToggleConfig = async (type: AvailableType) => {
    try {
      if (type.is_configured) {
        const config = configs.find(c => c.data_type === type.data_type)
        if (config) {
          await dataSupplyApi.updateConfig(config.id, { is_active: !type.is_active })
          message.success(type.is_active ? '已禁用' : '已启用')
        }
      } else {
        await dataSupplyApi.createConfig({
          data_type: type.data_type,
          data_name: type.data_name,
          model_name: type.model_name,
          is_active: true,
        })
        message.success('已启用')
      }
      fetchAvailableTypes()
      fetchConfigs()
      fetchDataTypeOptions()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '操作失败')
    }
  }

  const handleEditConfig = (config: ConfigItem) => {
    setEditingConfig(config)
    configForm.setFieldsValue({
      data_name: config.data_name,
      description: config.description,
      allowed_fields: config.allowed_fields_json ? JSON.parse(config.allowed_fields_json) : [],
      filter_fields: config.filter_fields_json ? JSON.parse(config.filter_fields_json) : [],
      mask_fields: (config as any).mask_fields_json ? JSON.parse((config as any).mask_fields_json) : [],
    })
    setConfigModalOpen(true)
  }

  const handleSaveConfig = async () => {
    try {
      const values = await configForm.validateFields()
      if (!editingConfig) return
      await dataSupplyApi.updateConfig(editingConfig.id, {
        data_name: values.data_name,
        description: values.description,
        allowed_fields_json: JSON.stringify(values.allowed_fields || []),
        filter_fields_json: JSON.stringify(values.filter_fields || []),
        mask_fields_json: JSON.stringify(values.mask_fields || []),
      })
      message.success('配置已更新')
      setConfigModalOpen(false)
      setEditingConfig(null)
      fetchConfigs()
      fetchAvailableTypes()
      fetchDataTypeOptions()
    } catch (e: any) {
      if (e.errorFields) return // 表单校验失败
      message.error(e?.response?.data?.detail || e.message || '保存失败')
    }
  }

  const handleDeleteConfig = async (id: number) => {
    try {
      await dataSupplyApi.deleteConfig(id)
      message.success('已删除')
      fetchConfigs()
      fetchAvailableTypes()
      fetchDataTypeOptions()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '删除失败')
    }
  }

  // ═══════════════════════════════════════════
  // API Key 操作
  // ═══════════════════════════════════════════

  const handleCreateApiKey = () => {
    setEditingApiKey(null)
    apiKeyForm.resetFields()
    apiKeyForm.setFieldsValue({ rate_limit: 100 })
    setApiKeyModalOpen(true)
  }

  const handleEditApiKey = (key: ApiKeyItem) => {
    setEditingApiKey(key)
    apiKeyForm.setFieldsValue({
      key_name: key.key_name,
      description: key.description,
      allowed_data_types: key.allowed_data_types_json ? JSON.parse(key.allowed_data_types_json) : [],
      rate_limit: key.rate_limit,
      expires_at: key.expires_at ? dayjs(key.expires_at) : undefined,
      ip_whitelist: key.ip_whitelist_json ? JSON.parse(key.ip_whitelist_json).join('\n') : '',
    })
    setApiKeyModalOpen(true)
  }

  const handleSaveApiKey = async () => {
    try {
      const values = await apiKeyForm.validateFields()
      // 解析 IP 白名单
      const ipList = values.ip_whitelist
        ? values.ip_whitelist.split('\n').map((s: string) => s.trim()).filter(Boolean)
        : []

      if (editingApiKey) {
        const updateData: any = {
          key_name: values.key_name,
          description: values.description,
          allowed_data_types_json: JSON.stringify(values.allowed_data_types || []),
          rate_limit: values.rate_limit,
          ip_whitelist_json: JSON.stringify(ipList),
        }
        if (values.expires_at) {
          updateData.expires_at = values.expires_at.toISOString()
        }
        await dataSupplyApi.updateApiKey(editingApiKey.id, updateData)
        message.success('API Key 已更新')
      } else {
        const createData: any = {
          key_name: values.key_name,
          description: values.description,
          allowed_data_types_json: JSON.stringify(values.allowed_data_types || []),
          rate_limit: values.rate_limit,
          ip_whitelist_json: JSON.stringify(ipList),
        }
        if (values.expires_at) {
          createData.expires_at = values.expires_at.toISOString()
        }
        const res: any = await dataSupplyApi.createApiKey(createData)
        message.success('API Key 已创建')
        const data = res.data || res
        setNewKeyVisible(data.api_key)
        setNewKeyInfo(data.app_key ? { app_key: data.app_key, app_secret: data.app_secret } : null)
      }
      setApiKeyModalOpen(false)
      fetchApiKeys()
    } catch (e: any) {
      if (e.errorFields) return
      message.error(e?.response?.data?.detail || e.message || '保存失败')
    }
  }

  const handleToggleApiKey = async (key: ApiKeyItem) => {
    try {
      await dataSupplyApi.updateApiKey(key.id, { is_active: !key.is_active })
      message.success(key.is_active ? '已禁用' : '已启用')
      fetchApiKeys()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '操作失败')
    }
  }

  const handleDeleteApiKey = async (id: number) => {
    try {
      await dataSupplyApi.deleteApiKey(id)
      message.success('已删除')
      fetchApiKeys()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '删除失败')
    }
  }

  // ═══════════════════════════════════════════
  // 渲染
  // ═══════════════════════════════════════════

  // ── Tab 1: 数据范围配置 ──
  const renderConfigsTab = () => {
    const filteredTypes = configSearchText
      ? availableTypes.filter(t =>
          t.data_name.includes(configSearchText) ||
          t.data_type.includes(configSearchText) ||
          t.model_name.includes(configSearchText)
        )
      : availableTypes

    const activeCount = availableTypes.filter(t => t.is_active).length
    const totalCount = availableTypes.length

    return (
      <div>
        {/* 概览统计 */}
        <Row gutter={16} style={{ marginBottom: 20 }}>
          <Col span={8}>
            <Card size="small" bordered={false} style={{ background: '#f0f5ff', borderRadius: 8 }}>
              <Statistic
                title="已启用数据类型"
                value={activeCount}
                suffix={`/ ${totalCount}`}
                prefix={<DatabaseOutlined style={{ color: '#1890ff' }} />}
                valueStyle={{ color: '#1890ff' }}
              />
            </Card>
          </Col>
          <Col span={8}>
            <Card size="small" bordered={false} style={{ background: '#f6ffed', borderRadius: 8 }}>
              <Statistic
                title="已配置"
                value={availableTypes.filter(t => t.is_configured).length}
                prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
                valueStyle={{ color: '#52c41a' }}
              />
            </Card>
          </Col>
          <Col span={8}>
            <Card size="small" bordered={false} style={{ background: '#fff7e6', borderRadius: 8 }}>
              <Statistic
                title="未配置"
                value={availableTypes.filter(t => !t.is_configured).length}
                prefix={<ExclamationCircleOutlined style={{ color: '#faad14' }} />}
                valueStyle={{ color: '#faad14' }}
              />
            </Card>
          </Col>
        </Row>

        {/* 搜索栏 */}
        <div style={{ marginBottom: 16 }}>
          <Input
            placeholder="搜索数据类型名称..."
            prefix={<SearchOutlined />}
            allowClear
            value={configSearchText}
            onChange={e => setConfigSearchText(e.target.value)}
            style={{ width: 300 }}
          />
        </div>

        <Table
          dataSource={filteredTypes}
          rowKey="model_name"
          loading={loading}
          pagination={false}
          size="middle"
          rowClassName={(record) => record.is_active ? '' : 'row-disabled'}
          columns={[
            {
              title: '数据类型',
              dataIndex: 'data_type',
              key: 'data_type',
              width: 160,
              render: (v: string, r: AvailableType) => (
                <Space>
                  <Tag color="blue" style={{ margin: 0 }}>
                    {r.data_name}
                  </Tag>
                  <Text type="secondary" style={{ fontSize: 12 }}>{v}</Text>
                </Space>
              ),
            },
            {
              title: '模型',
              dataIndex: 'model_name',
              key: 'model_name',
              width: 180,
              render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text>,
            },
            {
              title: '暴露字段',
              key: 'fields',
              width: 200,
              render: (_: any, r: AvailableType) => {
                const fields = r.allowed_fields?.length ? r.allowed_fields : r.default_fields
                const displayFields = fields.slice(0, 3)
                const remaining = fields.length - 3
                return (
                  <Space wrap size={4}>
                    {displayFields.map(f => (
                      <Tag key={f} style={{ fontSize: 11, margin: 0 }}>{f}</Tag>
                    ))}
                    {remaining > 0 && (
                      <Tooltip title={fields.slice(3).join(', ')}>
                        <Tag style={{ fontSize: 11, margin: 0 }}>+{remaining}</Tag>
                      </Tooltip>
                    )}
                  </Space>
                )
              },
            },
            {
              title: '筛选字段',
              key: 'filter_fields',
              width: 140,
              render: (_: any, r: AvailableType) => {
                if (!r.filter_fields?.length) return <Text type="secondary" style={{ fontSize: 12 }}>无</Text>
                return (
                  <Space wrap size={4}>
                    {r.filter_fields.slice(0, 2).map(f => (
                      <Tag key={f} color="orange" style={{ fontSize: 11, margin: 0 }}>{f}</Tag>
                    ))}
                    {r.filter_fields.length > 2 && (
                      <Tooltip title={r.filter_fields.slice(2).join(', ')}>
                        <Tag color="orange" style={{ fontSize: 11, margin: 0 }}>+{r.filter_fields.length - 2}</Tag>
                      </Tooltip>
                    )}
                  </Space>
                )
              },
            },
            {
              title: '状态',
              key: 'status',
              width: 100,
              render: (_: any, r: AvailableType) => (
                <Switch
                  checked={r.is_active}
                  onChange={() => handleToggleConfig(r)}
                  checkedChildren="启用"
                  unCheckedChildren="禁用"
                />
              ),
            },
            {
              title: '操作',
              key: 'action',
              width: 120,
              render: (_: any, r: AvailableType) => {
                const config = configs.find(c => c.data_type === r.data_type)
                return config ? (
                  <Space>
                    <Button size="small" type="link" icon={<SettingOutlined />} onClick={() => handleEditConfig(config)}>
                      编辑
                    </Button>
                    <Popconfirm title="确认删除此配置？" onConfirm={() => handleDeleteConfig(config.id)}>
                      <Button size="small" type="link" danger>删除</Button>
                    </Popconfirm>
                  </Space>
                ) : <Text type="secondary" style={{ fontSize: 12 }}>未配置</Text>
              },
            },
          ]}
        />

        <Modal
          title="编辑数据供给配置"
          open={configModalOpen}
          onOk={handleSaveConfig}
          onCancel={() => { setConfigModalOpen(false); setEditingConfig(null) }}
          width={640}
          destroyOnClose
        >
          <Form form={configForm} layout="vertical">
            <Form.Item name="data_name" label="数据名称" rules={[{ required: true, message: '请输入数据名称' }]}>
              <Input />
            </Form.Item>
            <Form.Item name="description" label="描述">
              <Input.TextArea rows={2} placeholder="可选，描述此数据供给的用途" />
            </Form.Item>
            <Form.Item name="allowed_fields" label="允许暴露的字段" rules={[{ required: true, message: '请至少添加一个字段' }]}>
              <Select mode="tags" placeholder="输入字段名后按回车添加" />
            </Form.Item>
            <Form.Item name="filter_fields" label="允许筛选的字段">
              <Select mode="tags" placeholder="输入字段名后按回车添加（可选）" />
            </Form.Item>
            <Form.Item name="mask_fields" label="需要脱敏的字段" tooltip="这些字段的值会自动脱敏（如手机号、邮箱等），支持自动识别 phone/mobile/email/credit_code/id_card 等字段名">
              <Select mode="tags" placeholder="输入字段名后按回车添加（可选）" />
            </Form.Item>
          </Form>
        </Modal>
      </div>
    )
  }

  // ── Tab 2: API Key 管理 ──
  const renderApiKeysTab = () => (
    <div>
      {newKeyVisible && (
        <Alert
          type="success"
          showIcon
          closable
          style={{ marginBottom: 16, borderRadius: 8 }}
          message="API Key 已创建（请妥善保存，以下信息仅显示一次）"
          description={
            <div>
              <div style={{ marginBottom: 8 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>API Key（兼容旧模式）</Text><br />
                <Space>
                  <Text code style={{ fontSize: 13, wordBreak: 'break-all' }}>{newKeyVisible}</Text>
                  <Button size="small" icon={<CopyOutlined />} onClick={() => copyToClipboard(newKeyVisible)}>复制</Button>
                </Space>
              </div>
              {newKeyInfo && (
                <>
                  <div style={{ marginBottom: 8 }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>AppKey（签名认证标识）</Text><br />
                    <Space>
                      <Text code style={{ fontSize: 13 }}>{newKeyInfo.app_key}</Text>
                      <Button size="small" icon={<CopyOutlined />} onClick={() => copyToClipboard(newKeyInfo.app_key)}>复制</Button>
                    </Space>
                  </div>
                  <div>
                    <Text type="secondary" style={{ fontSize: 12 }}>AppSecret（签名认证密钥，请务必保密）</Text><br />
                    <Space>
                      <Text code style={{ fontSize: 13, wordBreak: 'break-all' }}>{newKeyInfo.app_secret}</Text>
                      <Button size="small" icon={<CopyOutlined />} onClick={() => copyToClipboard(newKeyInfo.app_secret)}>复制</Button>
                    </Space>
                  </div>
                </>
              )}
            </div>
          }
          onClose={() => { setNewKeyVisible(null); setNewKeyInfo(null) }}
        />
      )}

      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <Badge count={apiKeyTotal} overflowCount={99} style={{ backgroundColor: '#1890ff' }}>
            <SafetyCertificateOutlined style={{ fontSize: 20, color: '#1890ff' }} />
          </Badge>
          <Text strong>共 {apiKeyTotal} 个 API Key</Text>
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateApiKey}>
          创建 API Key
        </Button>
      </div>

      <Table
        dataSource={apiKeys}
        rowKey="id"
        loading={loading}
        pagination={{ current: apiKeyPage, total: apiKeyTotal, pageSize: 20, onChange: setApiKeyPage, showTotal: t => `共 ${t} 条` }}
        size="middle"
        columns={[
          {
            title: '名称',
            dataIndex: 'key_name',
            key: 'key_name',
            width: 160,
            render: (v: string, r: ApiKeyItem) => (
              <Space>
                <Text strong={r.is_active}>{v}</Text>
                {!r.is_active && <Tag color="default">已禁用</Tag>}
              </Space>
            ),
          },
          {
            title: 'API Key',
            dataIndex: 'api_key',
            key: 'api_key',
            width: 200,
            render: (v: string) => (
              <Space>
                <Text code style={{ fontSize: 12 }}>{v.slice(0, 12)}...{v.slice(-4)}</Text>
                <Tooltip title="复制完整 Key">
                  <Button size="small" type="text" icon={<CopyOutlined />} onClick={() => copyToClipboard(v)} />
                </Tooltip>
              </Space>
            ),
          },
          {
            title: 'AppKey',
            dataIndex: 'app_key',
            key: 'app_key',
            width: 160,
            render: (v: string | null) => v ? (
              <Space>
                <Text code style={{ fontSize: 12 }}>{v}</Text>
                <Tooltip title="复制 AppKey">
                  <Button size="small" type="text" icon={<CopyOutlined />} onClick={() => copyToClipboard(v)} />
                </Tooltip>
              </Space>
            ) : <Text type="secondary">-</Text>,
          },
          {
            title: '描述',
            dataIndex: 'description',
            key: 'description',
            ellipsis: true,
            render: (v: string | null) => v || <Text type="secondary">-</Text>,
          },
          {
            title: '允许数据类型',
            dataIndex: 'allowed_data_types_json',
            key: 'allowed_types',
            width: 220,
            render: (v: string | null) => {
              if (!v) return <Tag color="green">全部</Tag>
              try {
                const types = JSON.parse(v)
                const displayTypes = types.slice(0, 2)
                const remaining = types.length - 2
                return (
                  <Space wrap size={4}>
                    {displayTypes.map((t: string) => (
                      <Tag key={t} color="blue" style={{ margin: 0 }}>{dataTypeLabelMap[t] || t}</Tag>
                    ))}
                    {remaining > 0 && (
                      <Tooltip title={types.slice(2).map((t: string) => dataTypeLabelMap[t] || t).join(', ')}>
                        <Tag style={{ margin: 0 }}>+{remaining}</Tag>
                      </Tooltip>
                    )}
                  </Space>
                )
              } catch {
                return <Tag>全部</Tag>
              }
            },
          },
          {
            title: '速率限制',
            dataIndex: 'rate_limit',
            key: 'rate_limit',
            width: 90,
            render: (v: number) => <Text>{v}/min</Text>,
          },
          {
            title: 'IP 白名单',
            dataIndex: 'ip_whitelist_json',
            key: 'ip_whitelist',
            width: 120,
            render: (v: string | null) => {
              if (!v) return <Tag color="green">不限</Tag>
              try {
                const ips = JSON.parse(v)
                if (!ips.length) return <Tag color="green">不限</Tag>
                return (
                  <Tooltip title={ips.join(', ')}>
                    <Tag color="blue">{ips.length} 个 IP</Tag>
                  </Tooltip>
                )
              } catch { return <Tag color="green">不限</Tag> }
            },
          },
          {
            title: '过期时间',
            dataIndex: 'expires_at',
            key: 'expires_at',
            width: 120,
            render: (v: string | null) => {
              if (!v) return <Tag color="green">永不过期</Tag>
              const isExpired = new Date(v) < new Date()
              return (
                <Text type={isExpired ? 'danger' : undefined}>
                  {v.slice(0, 10)}
                  {isExpired && ' (已过期)'}
                </Text>
              )
            },
          },
          {
            title: '状态',
            key: 'status',
            width: 80,
            render: (_: any, r: ApiKeyItem) => (
              <Switch checked={r.is_active} onChange={() => handleToggleApiKey(r)} size="small" />
            ),
          },
          {
            title: '操作',
            key: 'action',
            width: 100,
            render: (_: any, r: ApiKeyItem) => (
              <Space>
                <Button size="small" type="link" onClick={() => handleEditApiKey(r)}>编辑</Button>
                <Popconfirm title="确认删除此 API Key？" onConfirm={() => handleDeleteApiKey(r.id)}>
                  <Button size="small" type="link" danger>删除</Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title={editingApiKey ? '编辑 API Key' : '创建 API Key'}
        open={apiKeyModalOpen}
        onOk={handleSaveApiKey}
        onCancel={() => { setApiKeyModalOpen(false); setEditingApiKey(null) }}
        width={560}
        destroyOnClose
      >
        <Form form={apiKeyForm} layout="vertical">
          <Form.Item name="key_name" label="名称（外部系统名）" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如：MES系统、WMS系统" />
          </Form.Item>
          <Form.Item name="description" label="用途说明">
            <Input.TextArea rows={2} placeholder="描述此 Key 的用途" />
          </Form.Item>
          <Form.Item name="allowed_data_types" label="允许访问的数据类型" rules={[{ required: true, message: '请选择至少一个数据类型' }]}>
            <Select mode="multiple" options={dataTypeOptions} placeholder="选择允许访问的数据类型" />
          </Form.Item>
          <Form.Item name="rate_limit" label="速率限制（每分钟请求数）" rules={[{ required: true, message: '请输入速率限制' }]}>
            <InputNumber min={1} max={10000} style={{ width: '100%' }} placeholder="100" />
          </Form.Item>
          <Form.Item name="ip_whitelist" label="IP 白名单（每行一个，留空则不限制）" tooltip="限制允许调用的来源 IP，留空表示不限制">
            <Input.TextArea rows={3} placeholder={"192.168.1.100\n10.0.0.0/24"} />
          </Form.Item>
          <Form.Item name="expires_at" label="过期时间（可选）">
            <DatePicker
              showTime
              style={{ width: '100%' }}
              placeholder="不选则永不过期"
              disabledDate={(current) => current && current < dayjs().startOf('day')}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )

  // ── Tab 3: 调用日志 ──
  const renderCallLogsTab = () => {
    const successRate = statistics && statistics.total_calls > 0
      ? ((statistics.success_calls / statistics.total_calls) * 100).toFixed(1)
      : null

    return (
      <div>
        {/* 统计卡片 */}
        {statistics && (
          <Row gutter={16} style={{ marginBottom: 20 }}>
            <Col span={6}>
              <Card size="small" bordered={false} style={{ background: '#f0f5ff', borderRadius: 8 }}>
                <Statistic
                  title="总调用次数"
                  value={statistics.total_calls}
                  prefix={<BarChartOutlined style={{ color: '#1890ff' }} />}
                  valueStyle={{ color: '#1890ff' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" bordered={false} style={{ background: '#f6ffed', borderRadius: 8 }}>
                <Statistic
                  title="成功 / 成功率"
                  value={statistics.success_calls}
                  suffix={successRate ? ` (${successRate}%)` : ''}
                  prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
                  valueStyle={{ color: '#52c41a' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" bordered={false} style={{ background: statistics?.failed_calls ? '#fff2f0' : '#fafafa', borderRadius: 8 }}>
                <Statistic
                  title="失败"
                  value={statistics.failed_calls}
                  prefix={<CloseCircleOutlined style={{ color: statistics?.failed_calls ? '#ff4d4f' : '#d9d9d9' }} />}
                  valueStyle={{ color: statistics?.failed_calls ? '#ff4d4f' : '#999' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" bordered={false} style={{ background: '#fafafa', borderRadius: 8 }}>
                <Statistic
                  title="平均耗时"
                  value={statistics.avg_duration_ms?.toFixed(1) || '-'}
                  suffix="ms"
                  prefix={<ClockCircleOutlined style={{ color: '#722ed1' }} />}
                  valueStyle={{ color: '#722ed1' }}
                />
              </Card>
            </Col>
          </Row>
        )}

        {/* 筛选栏 */}
        <Card size="small" style={{ marginBottom: 16, borderRadius: 8 }} bordered={false}>
          <Space wrap size={12}>
            <Select
              allowClear
              placeholder="按数据类型筛选"
              style={{ width: 200 }}
              options={dataTypeOptions}
              value={logFilters.data_type || undefined}
              onChange={(v) => {
                setCallLogPage(1)
                setLogFilters(prev => ({ ...prev, data_type: v }))
              }}
            />
            <RangePicker
              value={logFilters.dateRange || null}
              onChange={(dates) => {
                setCallLogPage(1)
                setLogFilters(prev => ({ ...prev, dateRange: dates }))
              }}
            />
            <Button
              icon={<ReloadOutlined />}
              onClick={() => { setLogFilters({}); setCallLogPage(1) }}
            >
              重置
            </Button>
          </Space>
        </Card>

        {/* 按数据类型分布 */}
        {statistics && Object.keys(statistics.by_data_type).length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <Text strong style={{ marginBottom: 8, display: 'block' }}>按数据类型分布</Text>
            <Space wrap size={8}>
              {Object.entries(statistics.by_data_type)
                .sort(([, a], [, b]) => b - a)
                .map(([type, count]) => (
                  <Tag
                    key={type}
                    color="blue"
                    style={{ fontSize: 12, padding: '2px 8px' }}
                  >
                    {dataTypeLabelMap[type] || type}: {count}
                  </Tag>
                ))}
            </Space>
          </div>
        )}

        {/* 按 API Key 分布 */}
        {statistics && Object.keys(statistics.by_api_key).length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <Text strong style={{ marginBottom: 8, display: 'block' }}>按 API Key 分布</Text>
            <Space wrap size={8}>
              {Object.entries(statistics.by_api_key)
                .sort(([, a], [, b]) => b - a)
                .map(([name, count]) => (
                  <Tag key={name} color="geekblue" style={{ fontSize: 12, padding: '2px 8px' }}>
                    {name}: {count}
                  </Tag>
                ))}
            </Space>
          </div>
        )}

        <Table
          dataSource={callLogs}
          rowKey="id"
          loading={loading}
          pagination={{
            current: callLogPage,
            total: callLogTotal,
            pageSize: 20,
            onChange: setCallLogPage,
            showTotal: t => `共 ${t} 条`,
          }}
          scroll={{ x: 1200 }}
          size="middle"
          locale={{ emptyText: <Empty description="暂无调用日志" /> }}
          columns={[
            {
              title: '时间',
              dataIndex: 'called_at',
              key: 'called_at',
              width: 170,
              render: (v: string) => v ? <Text style={{ fontSize: 12 }}>{v.slice(0, 19).replace('T', ' ')}</Text> : '-',
            },
            {
              title: 'API Key',
              dataIndex: 'api_key_name',
              key: 'api_key_name',
              width: 140,
              render: (v: string | null) => v || <Text type="secondary">-</Text>,
            },
            {
              title: '数据类型',
              dataIndex: 'data_type',
              key: 'data_type',
              width: 120,
              render: (v: string) => (
                <Tag color="blue">
                  {dataTypeLabelMap[v] || v}
                </Tag>
              ),
            },
            {
              title: '状态',
              dataIndex: 'response_status',
              key: 'status',
              width: 80,
              render: (v: number | null) => {
                if (v === 200) return <Badge status="success" text="200" />
                if (v === 500) return <Badge status="error" text={String(v)} />
                return <Badge status="warning" text={String(v || '-')} />
              },
            },
            {
              title: '返回条数',
              dataIndex: 'response_count',
              key: 'count',
              width: 90,
              render: (v: number) => <Text>{v}</Text>,
            },
            {
              title: '耗时',
              dataIndex: 'duration_ms',
              key: 'duration',
              width: 90,
              render: (v: number | null) => {
                if (!v) return '-'
                const ms = Number(v)
                const color = ms > 1000 ? '#ff4d4f' : ms > 500 ? '#faad14' : '#52c41a'
                return <Text style={{ color }}>{ms.toFixed(1)}ms</Text>
              },
            },
            {
              title: 'IP',
              dataIndex: 'ip_address',
              key: 'ip',
              width: 130,
              render: (v: string | null) => v ? <Text style={{ fontSize: 12 }}>{v}</Text> : <Text type="secondary">-</Text>,
            },
            {
              title: '请求参数',
              dataIndex: 'request_params_json',
              key: 'params',
              ellipsis: true,
              render: (v: string | null) => v ? (
                <Tooltip title={v}>
                  <Text ellipsis style={{ maxWidth: 200, fontSize: 12 }}>{v}</Text>
                </Tooltip>
              ) : <Text type="secondary">-</Text>,
            },
          ]}
        />
      </div>
    )
  }

  // ── Tab 4: 使用说明 ──
  const generateGuideMarkdown = () => {
    const host = window.location.host
    const baseUrl = `http://${host}/api/v1/basicdata/data-supply`

    const typeRows = dataTypeOptions.map(o => `| ${o.value} | ${o.label} | （由配置决定） |`).join('\n')

    return `# 数据供给 API 使用说明

## 1. 接入流程

1. 在 **数据范围配置** 中启用需要的数据类型
2. 在 **API Key 管理** 中创建一个 API Key，选择允许访问的数据类型
3. 妥善保存生成的 AppKey + AppSecret（仅显示一次），将其配置到外部系统中
4. 外部系统调用 API 时，使用 HMAC-SHA256 签名认证

## 2. 认证方式

支持两种认证方式，**推荐使用签名认证**：

### 方式一：签名认证（推荐）

每次请求携带以下三个请求头：

| 请求头 | 说明 | 示例 |
|--------|------|------|
| \`X-App-Key\` | 应用标识（AppKey） | \`ak_a1b2c3d4e5f6g7h8\` |
| \`X-Timestamp\` | 当前 Unix 时间戳（秒） | \`1719000000\` |
| \`X-Signature\` | HMAC-SHA256 签名 | \`a3f2b1c4d5e6...\` |

**签名算法：**

\`\`\`
1. 构造待签名字符串 = timestamp + app_key + data_type + query_string
   例如：1719000000ak_a1b2c3d4e5f6g7h8materialspage=1&page_size=20

2. 使用 AppSecret 对待签名字符串做 HMAC-SHA256 签名

3. 将签名结果转为十六进制字符串，放入 X-Signature 请求头
\`\`\`

**防重放：** 时间戳与服务器时间差超过 5 分钟，请求将被拒绝。

### 方式二：API Key 认证（兼容旧模式）

| 请求头 | 说明 | 示例 |
|--------|------|------|
| \`X-API-Key\` | 数据供给 API Key | \`spc_a1b2c3d4e5f6...\` |

> 注意：API Key 明文传输，安全性低于签名认证，建议仅用于内部测试。

## 3. API 接口

### 3.1 查询数据列表

\`GET ${baseUrl}/data/{data_type}\`

| 参数 | 位置 | 必填 | 说明 |
|------|------|------|------|
| \`data_type\` | Path | 是 | 数据类型标识 |
| \`page\` | Query | 否 | 页码，默认 1 |
| \`page_size\` | Query | 否 | 每页条数，默认 20，最大 200 |
| \`keyword\` | Query | 否 | 关键字搜索 |
| \`updated_after\` | Query | 否 | 增量同步：ISO 8601 时间，只返回此时间后更新的数据 |

### 3.2 查询单条数据

\`GET ${baseUrl}/data/{data_type}/{record_id}\`

### 3.3 响应格式

\`\`\`json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [...],
    "total": 100,
    "page": 1,
    "page_size": 20
  }
}
\`\`\`

## 4. 可用数据类型

| data_type | 中文名 | 暴露字段 |
|-----------|--------|----------|
${typeRows}

## 5. 调用示例

### Python（签名认证）

\`\`\`python
import hmac
import hashlib
import time
import requests

BASE_URL = "${baseUrl}"
APP_KEY = "ak_xxxxxxxx"
APP_SECRET = "your_app_secret"

def make_signature(app_key, app_secret, data_type, query_string=""):
    timestamp = str(int(time.time()))
    string_to_sign = f"{timestamp}{app_key}{data_type}{query_string}"
    signature = hmac.new(
        app_secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return timestamp, signature

# 查询物料列表
data_type = "materials"
query_string = "page=1&page_size=20"
timestamp, signature = make_signature(APP_KEY, APP_SECRET, data_type, query_string)

resp = requests.get(
    f"{BASE_URL}/data/{data_type}",
    params={"page": 1, "page_size": 20},
    headers={
        "X-App-Key": APP_KEY,
        "X-Timestamp": timestamp,
        "X-Signature": signature,
    },
)
print(resp.json())

# 增量同步：只获取最近更新的数据
resp = requests.get(
    f"{BASE_URL}/data/{data_type}",
    params={"updated_after": "2024-01-01T00:00:00"},
    headers={
        "X-App-Key": APP_KEY,
        "X-Timestamp": timestamp,
        "X-Signature": signature,
    },
)
print(resp.json())
\`\`\`

### cURL（签名认证）

\`\`\`bash
# 1. 生成签名（需要 openssl 或 python）
TIMESTAMP=$(date +%s)
APP_KEY="ak_xxxxxxxx"
APP_SECRET="your_app_secret"
DATA_TYPE="materials"
STRING_TO_SIGN="\${TIMESTAMP}\${APP_KEY}\${DATA_TYPE}"
SIGNATURE=$(echo -n "\$STRING_TO_SIGN" | openssl dgst -sha256 -hmac "\$APP_SECRET" | awk '{print $NF}')

# 2. 发送请求
curl -X GET "${baseUrl}/data/materials?page=1&page_size=20" \\
  -H "X-App-Key: \$APP_KEY" \\
  -H "X-Timestamp: \$TIMESTAMP" \\
  -H "X-Signature: \$SIGNATURE"
\`\`\`

### Java（签名认证）

\`\`\`java
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.net.http.*;
import java.net.URI;

String baseUrl = "${baseUrl}";
String appKey = "ak_xxxxxxxx";
String appSecret = "your_app_secret";
String dataType = "materials";

// 生成签名
String timestamp = String.valueOf(System.currentTimeMillis() / 1000);
String stringToSign = timestamp + appKey + dataType;
Mac mac = Mac.getInstance("HmacSHA256");
mac.init(new SecretKeySpec(appSecret.getBytes(), "HmacSHA256"));
String signature = HexFormat.of().formatHex(mac.doFinal(stringToSign.getBytes()));

// 发送请求
HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create(baseUrl + "/data/" + dataType + "?page=1&page_size=20"))
    .header("X-App-Key", appKey)
    .header("X-Timestamp", timestamp)
    .header("X-Signature", signature)
    .build();
HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
System.out.println(response.body());
\`\`\`

## 6. 安全机制

| 机制 | 说明 |
|------|------|
| HMAC-SHA256 签名 | AppSecret 不在网络传输，仅用于本地签名计算 |
| 时间戳校验 | 请求时间与服务器时间差超过 5 分钟则拒绝，防重放攻击 |
| IP 白名单 | 可为每个 API Key 配置允许的来源 IP |
| 字段级脱敏 | 手机号、邮箱等敏感字段自动脱敏（如 138****1234） |
| 数据类型权限 | 每个 API Key 只能访问被授权的数据类型 |

## 7. 错误码说明

| HTTP 状态码 | 含义 | 排查建议 |
|-------------|------|----------|
| 401 | 缺少认证信息 | 检查是否携带了 X-App-Key/X-Timestamp/X-Signature 或 X-API-Key |
| 403 | 认证失败或无权限 | 签名不匹配、Key 已过期、IP 不在白名单、或无权访问该数据类型 |
| 404 | 数据类型未启用或记录不存在 | 在数据范围配置中启用该数据类型 |
| 500 | 服务器内部错误 | 联系管理员排查 |
`
  }

  const handleExportMarkdown = () => {
    const md = generateGuideMarkdown()
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = '数据供给API使用说明.md'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    message.success('文档已导出')
  }

  const renderGuideTab = () => (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
        <Button type="primary" icon={<DownloadOutlined />} onClick={handleExportMarkdown}>
          导出 Markdown 文档
        </Button>
      </div>

      <Card title="1. 接入流程" style={{ marginBottom: 16 }} size="small">
        <ol style={{ paddingLeft: 20, margin: 0, lineHeight: 2.2 }}>
          <li>在 <Text strong>数据范围配置</Text> 中启用需要的数据类型</li>
          <li>在 <Text strong>API Key 管理</Text> 中创建一个 API Key，选择允许访问的数据类型</li>
          <li>妥善保存生成的 <Text code>AppKey</Text> + <Text code>AppSecret</Text>（仅显示一次），将其配置到外部系统中</li>
          <li>外部系统调用 API 时，使用 HMAC-SHA256 签名认证</li>
        </ol>
      </Card>

      <Card title="2. 认证方式" style={{ marginBottom: 16 }} size="small">
        <Text>支持两种认证方式，<Text strong>推荐使用签名认证</Text>：</Text>

        <div style={{ marginTop: 12, marginBottom: 8 }}>
          <Text strong>方式一：签名认证（推荐）</Text>
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, marginBottom: 8 }}>
          <thead>
            <tr style={{ background: '#fafafa' }}>
              <th style={{ padding: '8px 12px', border: '1px solid #f0f0f0', textAlign: 'left' }}>请求头</th>
              <th style={{ padding: '8px 12px', border: '1px solid #f0f0f0', textAlign: 'left' }}>说明</th>
              <th style={{ padding: '8px 12px', border: '1px solid #f0f0f0', textAlign: 'left' }}>示例</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}><Text code>X-App-Key</Text></td>
              <td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}>应用标识</td>
              <td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}><Text code>ak_a1b2c3d4e5f6g7h8</Text></td>
            </tr>
            <tr>
              <td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}><Text code>X-Timestamp</Text></td>
              <td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}>Unix 时间戳（秒）</td>
              <td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}><Text code>1719000000</Text></td>
            </tr>
            <tr>
              <td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}><Text code>X-Signature</Text></td>
              <td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}>HMAC-SHA256 签名</td>
              <td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}><Text code>a3f2b1c4d5e6...</Text></td>
            </tr>
          </tbody>
        </table>
        <Alert type="info" style={{ marginBottom: 12 }} message={
          <div>
            <Text strong>签名算法：</Text><br />
            <Text>1. 构造待签名字符串 = <Text code>timestamp + app_key + data_type + query_string</Text></Text><br />
            <Text>2. 使用 AppSecret 对待签名字符串做 HMAC-SHA256</Text><br />
            <Text>3. 将结果转为十六进制字符串放入 X-Signature</Text><br />
            <Text type="secondary">防重放：时间戳与服务器时间差超过 5 分钟，请求将被拒绝</Text>
          </div>
        } />

        <div style={{ marginBottom: 8 }}>
          <Text strong>方式二：API Key 认证（兼容旧模式）</Text>
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#fafafa' }}>
              <th style={{ padding: '8px 12px', border: '1px solid #f0f0f0', textAlign: 'left' }}>请求头</th>
              <th style={{ padding: '8px 12px', border: '1px solid #f0f0f0', textAlign: 'left' }}>说明</th>
              <th style={{ padding: '8px 12px', border: '1px solid #f0f0f0', textAlign: 'left' }}>示例</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}><Text code>X-API-Key</Text></td>
              <td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}>数据供给 API Key</td>
              <td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}><Text code>spc_a1b2c3d4e5f6...</Text></td>
            </tr>
          </tbody>
        </table>
        <Alert type="warning" style={{ marginTop: 8 }} message="API Key 明文传输，安全性低于签名认证，建议仅用于内部测试。" />
      </Card>

      <Card title="3. 安全机制" style={{ marginBottom: 16 }} size="small">
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#fafafa' }}>
              <th style={{ padding: '8px 12px', border: '1px solid #f0f0f0', textAlign: 'left' }}>机制</th>
              <th style={{ padding: '8px 12px', border: '1px solid #f0f0f0', textAlign: 'left' }}>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr><td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}>HMAC-SHA256 签名</td><td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}>AppSecret 不在网络传输，仅用于本地签名计算</td></tr>
            <tr><td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}>时间戳校验</td><td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}>请求时间与服务器时间差超过 5 分钟则拒绝，防重放攻击</td></tr>
            <tr><td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}>IP 白名单</td><td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}>可为每个 API Key 配置允许的来源 IP</td></tr>
            <tr><td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}>字段级脱敏</td><td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}>手机号、邮箱等敏感字段自动脱敏（如 138****1234）</td></tr>
            <tr><td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}>数据类型权限</td><td style={{ padding: '8px 12px', border: '1px solid #f0f0f0' }}>每个 API Key 只能访问被授权的数据类型</td></tr>
          </tbody>
        </table>
      </Card>

      <Card title="4. 可用数据类型" style={{ marginBottom: 16 }} size="small">
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#fafafa' }}>
              <th style={{ padding: '6px 12px', border: '1px solid #f0f0f0', textAlign: 'left' }}>data_type</th>
              <th style={{ padding: '6px 12px', border: '1px solid #f0f0f0', textAlign: 'left' }}>中文名</th>
            </tr>
          </thead>
          <tbody>
            {dataTypeOptions.map(opt => (
              <tr key={opt.value}>
                <td style={{ padding: '6px 12px', border: '1px solid #f0f0f0' }}><Tag>{opt.value}</Tag></td>
                <td style={{ padding: '6px 12px', border: '1px solid #f0f0f0' }}>{opt.label}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="5. 错误码说明" size="small">
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#fafafa' }}>
              <th style={{ padding: '6px 12px', border: '1px solid #f0f0f0', textAlign: 'left' }}>HTTP 状态码</th>
              <th style={{ padding: '6px 12px', border: '1px solid #f0f0f0', textAlign: 'left' }}>含义</th>
              <th style={{ padding: '6px 12px', border: '1px solid #f0f0f0', textAlign: 'left' }}>排查建议</th>
            </tr>
          </thead>
          <tbody>
            <tr><td style={{ padding: '6px 12px', border: '1px solid #f0f0f0' }}><Tag color="red">401</Tag></td><td style={{ padding: '6px 12px', border: '1px solid #f0f0f0' }}>缺少认证信息</td><td style={{ padding: '6px 12px', border: '1px solid #f0f0f0' }}>检查是否携带了 X-App-Key/X-Timestamp/X-Signature 或 X-API-Key</td></tr>
            <tr><td style={{ padding: '6px 12px', border: '1px solid #f0f0f0' }}><Tag color="red">403</Tag></td><td style={{ padding: '6px 12px', border: '1px solid #f0f0f0' }}>认证失败或无权限</td><td style={{ padding: '6px 12px', border: '1px solid #f0f0f0' }}>签名不匹配、Key 已过期、IP 不在白名单、或无权访问该数据类型</td></tr>
            <tr><td style={{ padding: '6px 12px', border: '1px solid #f0f0f0' }}><Tag color="orange">404</Tag></td><td style={{ padding: '6px 12px', border: '1px solid #f0f0f0' }}>数据类型未启用或记录不存在</td><td style={{ padding: '6px 12px', border: '1px solid #f0f0f0' }}>在数据范围配置中启用该数据类型</td></tr>
            <tr><td style={{ padding: '6px 12px', border: '1px solid #f0f0f0' }}><Tag color="red">500</Tag></td><td style={{ padding: '6px 12px', border: '1px solid #f0f0f0' }}>服务器内部错误</td><td style={{ padding: '6px 12px', border: '1px solid #f0f0f0' }}>联系管理员排查</td></tr>
          </tbody>
        </table>
      </Card>
    </div>
  )

  return (
    <div style={{ padding: 0 }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <ApiOutlined style={{ fontSize: 22, color: '#1890ff' }} />
          <Text strong style={{ fontSize: 18 }}>数据供给</Text>
        </div>
        <Text type="secondary">管理对外数据供给接口，配置数据范围、API Key 和监控调用情况</Text>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        type="card"
        items={[
          {
            key: 'configs',
            label: <span><DatabaseOutlined /> 数据范围配置</span>,
            children: renderConfigsTab(),
          },
          {
            key: 'api-keys',
            label: <span><KeyOutlined /> API Key 管理</span>,
            children: renderApiKeysTab(),
          },
          {
            key: 'call-logs',
            label: <span><BarChartOutlined /> 调用日志</span>,
            children: renderCallLogsTab(),
          },
          {
            key: 'guide',
            label: <span><BookOutlined /> 使用说明</span>,
            children: renderGuideTab(),
          },
        ]}
      />
    </div>
  )
}
