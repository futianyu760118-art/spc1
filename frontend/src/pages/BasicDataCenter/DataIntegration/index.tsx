import { useState, useEffect, useCallback } from 'react'
import {
  Upload, Button, message, Alert, List, Space, Card, Tag,
  InputNumber, Tooltip, Spin, Descriptions, Collapse, Modal, Table,
  Select, notification as antNotification,
} from 'antd'
import {
  UploadOutlined, DownloadOutlined, FileExcelOutlined, SyncOutlined,
  CheckCircleOutlined, WarningOutlined,
  InfoCircleOutlined, ClockCircleOutlined, PlusOutlined,
  HistoryOutlined, ReloadOutlined,
} from '@ant-design/icons'
import { importExportApi, dashboardApi, notificationApi } from '../../../services/api'
import dayjs from 'dayjs'

type SyncType = string

interface SyncResult {
  synced?: number
  created?: number
  updated?: number
  skipped?: number
  errors?: string[]
  roles_from_position?: number
  users_created?: number
  users_updated?: number
  users_skipped?: number
  orders?: SyncResult
  materials?: SyncResult
  purchase_orders?: SyncResult
}

interface ConfigStatus {
  enabled: boolean
  erp_db_configured: boolean
  types: Record<string, {
    label: string
    configured: boolean
    is_active: boolean
    has_sql: boolean
    has_mapping: boolean
    sync_enabled?: boolean
  }>
}

// Excel 导入（备份）支持的特殊类型及其必填字段
const EXCEL_IMPORT_TYPES: Record<string, string> = {
  orders: 'order_no, line_no, customer, product_code, product_name, order_qty, promised_date, planned_start_date, owner',
  materials: 'order_no, line_no, material_code, material_name, req_qty, req_date',
  purchase_orders: 'po_no, material_code, supplier_code, supplier_name, po_qty, po_status, eta, owner',
}

// 需要特殊提示信息的类型
const TYPE_ALERTS: Record<string, { message: string; description: string }> = {
  positions: {
    message: '岗位同步会自动创建对应的系统角色',
    description: '同步岗位时，系统会根据岗位名称自动匹配权限分类并创建角色，岗位与角色自动关联。人员同步时，系统用户将通过岗位ID获取对应的角色权限。',
  },
  employees: {
    message: '人员同步会自动创建系统用户并分配岗位角色',
    description: '同步人员时，系统会根据员工的岗位ID自动匹配对应角色，并创建或更新系统用户。请确保先同步岗位数据，再同步人员数据。',
  },
}

function SyncResultCard({ result, type, label }: { result: SyncResult; type: string; label?: string }) {
  const errors = result.errors || []
  const hasErrors = errors.length > 0
  const isEmployees = type === 'employees'
  const extraItems: React.ReactNode[] = []

  if (isEmployees) {
    if (result.users_created != null) {
      extraItems.push(
        <Descriptions.Item key="users_created" label="用户创建">
          <Tag color="purple">{result.users_created}</Tag>
        </Descriptions.Item>
      )
    }
    if (result.users_updated != null) {
      extraItems.push(
        <Descriptions.Item key="users_updated" label="用户更新">
          <Tag color="geekblue">{result.users_updated}</Tag>
        </Descriptions.Item>
      )
    }
    if (result.roles_from_position != null) {
      extraItems.push(
        <Descriptions.Item key="roles_from_position" label="通过岗位获取角色">
          <Tag color="cyan">{result.roles_from_position}</Tag>
        </Descriptions.Item>
      )
    }
  }

  return (
    <Card
      size="small"
      style={{
        borderColor: hasErrors ? '#faad14' : '#52c41a',
        background: hasErrors ? '#fffbe6' : '#f6ffed',
      }}
    >
      <Descriptions size="small" column={extraItems.length > 0 ? 5 : 5} style={{ marginBottom: hasErrors ? 8 : 0 }}>
        <Descriptions.Item label="类型">
          <Tag color="blue">{label || type}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="新增">
          <Tag color="green">{result.created ?? 0}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="更新">
          <Tag color="orange">{result.updated ?? 0}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="跳过">
          <Tag>{result.skipped ?? 0}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="错误">
          <Tag color={hasErrors ? 'red' : 'default'}>{errors.length}</Tag>
        </Descriptions.Item>
        {extraItems}
      </Descriptions>
      {hasErrors && (
        <Collapse
          size="small"
          items={[{
            key: '1',
            label: <span style={{ color: '#d48806', fontSize: 12 }}><WarningOutlined /> 查看 {errors.length} 条错误详情</span>,
            children: (
              <List
                size="small"
                dataSource={errors.slice(0, 20)}
                renderItem={(item: string) => (
                  <List.Item style={{ padding: '4px 0', fontSize: 12 }}>{item}</List.Item>
                )}
              />
            ),
          }]}
        />
      )}
    </Card>
  )
}

export default function DataImport() {
  const [importResult, setImportResult] = useState<any>(null)
  const [syncResults, setSyncResults] = useState<Record<string, SyncResult & { timestamp: string }>>({})
  const [syncLoading, setSyncLoading] = useState<Record<string, boolean>>({})
  const [syncAllLoading, setSyncAllLoading] = useState(false)
  const [hours, setHours] = useState(24)
  const [configStatus, setConfigStatus] = useState<ConfigStatus | null>(null)
  const [configLoading, setConfigLoading] = useState(false)
  const [selectedOrders, setSelectedOrders] = useState<string[]>([])
  const [orderModalVisible, setOrderModalVisible] = useState(false)
  const [ordersData, setOrdersData] = useState<any[]>([])
  const [ordersLoading, setOrdersLoading] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])

  const loadConfigStatus = useCallback(async () => {
    setConfigLoading(true)
    try {
      const res: any = await importExportApi.getSyncConfigStatus()
      setConfigStatus(res.data)
    } catch {
      // 非致命：静默失败
    } finally {
      setConfigLoading(false)
    }
  }, [])

  const loadOrdersData = useCallback(async () => {
    setOrdersLoading(true)
    try {
      const res: any = await importExportApi.getErpOrders()
      setOrdersData(res.data)
    } catch {
      // handled by interceptor
    } finally {
      setOrdersLoading(false)
    }
  }, [])

  const [selectedType, setSelectedType] = useState<string>('')

  useEffect(() => {
    loadConfigStatus()
  }, [loadConfigStatus])

  // 配置加载后默认选中第一个类型
  useEffect(() => {
    if (configStatus && !selectedType) {
      const firstType = Object.keys(configStatus.types)[0]
      if (firstType) setSelectedType(firstType)
    }
  }, [configStatus, selectedType])

  const getLabel = (type: string) => configStatus?.types?.[type]?.label || type

  const handleOpenOrderModal = async () => {
    setOrderModalVisible(true)
    await loadOrdersData()
    // 恢复已选订单的行keys
    if (selectedOrders.length > 0) {
      const selectedKeys = ordersData
        .filter(order => selectedOrders.includes(order.order_no))
        .map(order => `${order.order_no}-${order.line_no}`)
      setSelectedRowKeys(selectedKeys)
    } else {
      setSelectedRowKeys([])
    }
  }

  const handleConfirmOrderSelection = () => {
    const selectedOrdersData = ordersData.filter(order =>
      selectedRowKeys.includes(`${order.order_no}-${order.line_no}`)
    )
    const orderNumbers = [...new Set(selectedOrdersData.map(o => o.order_no))]
    setSelectedOrders(orderNumbers)
    setOrderModalVisible(false)
  }

  const handleClearOrderSelection = () => {
    setSelectedOrders([])
    setSelectedRowKeys([])
    setOrderModalVisible(false)
  }

  const handleUpload = async (file: File, type: SyncType) => {
    try {
      let res: any
      if (type === 'orders') res = await importExportApi.importOrders(file)
      else if (type === 'materials') res = await importExportApi.importMaterials(file)
      else res = await importExportApi.importPurchaseOrders(file)
      setImportResult({ ...res.data, type })
      message.success('导入完成')
    } catch {
      message.error('导入失败')
    }
    return false
  }

  const handleExportWeekly = async () => {
    try {
      const res: any = await importExportApi.exportWeeklyReport()
      const url = window.URL.createObjectURL(new Blob([res]))
      const link = document.createElement('a')
      link.href = url
      link.download = 'weekly_report.xlsx'
      link.click()
    } catch {
      message.error('导出失败')
    }
  }

  const [syncLogs, setSyncLogs] = useState<any[]>([])
  const [syncLogsLoading, setSyncLogsLoading] = useState(false)
  const [syncLogFilter, setSyncLogFilter] = useState<string>('')

  const fetchSyncLogs = async () => {
    setSyncLogsLoading(true)
    try {
      const res: any = await importExportApi.listSyncTasks({ limit: 30, sync_type: syncLogFilter || undefined, status: undefined })
      setSyncLogs(res.data || [])
    } catch {
      message.error('加载同步日志失败')
    } finally {
      setSyncLogsLoading(false)
    }
  }

  useEffect(() => { fetchSyncLogs() }, [syncLogFilter])

  // 轮询：如果有 running/pending 任务，自动刷新
  useEffect(() => {
    const hasActive = syncLogs.some(l => l.status === 'running' || l.status === 'pending')
    if (!hasActive) return
    const timer = setTimeout(() => { fetchSyncLogs() }, 3000)
    return () => clearTimeout(timer)
  }, [syncLogs])

  // 创建同步完成通知
  const createSyncNotification = async (type: SyncType, result: SyncResult, success: boolean) => {
    try {
      const title = success ? '数据同步完成' : '数据同步失败'
      const content = success 
        ? `${getLabel(type)} 同步完成：新增 ${result.created ?? 0} 条，更新 ${result.updated ?? 0} 条`
        : `${getLabel(type)} 同步失败：${result.errors?.join('；') || '未知错误'}`
      
      await notificationApi.create({
        title,
        content,
        type: 'system',
        priority: success ? 'normal' : 'important'
      })
    } catch (error) {
      console.error('创建通知失败:', error)
    }
  }

  const handleSync = async (type: SyncType) => {
    setSyncLoading(prev => ({ ...prev, [type]: true }))
    try {
      const params: any = { hours }
      if ((type === 'orders' || type === 'materials') && selectedOrders.length > 0) {
        params.order_numbers = selectedOrders
      }

      // 提交异步同步任务
      const res: any = await importExportApi.syncData(type, params)
      const taskId = res.data?.task_id
      if (!taskId) {
        // 兼容旧版直接返回结果
        const data = res.data as SyncResult
        const ts = new Date().toLocaleString()
        setSyncResults(prev => ({ ...prev, [type]: { ...data, timestamp: ts } }))
        const errors = data.errors || []
        const success = errors.length === 0
        if (errors.length > 0) {
          message.warning(`${getLabel(type)} 同步完成，但有 ${errors.length} 条错误`)
        } else {
          message.success(`${getLabel(type)} 同步完成：新增 ${data.created ?? 0}，更新 ${data.updated ?? 0}`)
        }
        // 创建通知
        await createSyncNotification(type, data, success)
        // 显示顶部栏提示
        if (success) {
          antNotification.success({
            message: '同步完成',
            description: `${getLabel(type)} 同步已完成，请查看顶部栏通知`,
            placement: 'topRight',
            duration: 4,
          })
        }
        return
      }

      // 轮询任务状态
      message.info(`${getLabel(type)} 同步任务已提交...`)
      const pollTask = async () => {
        try {
          const taskRes: any = await importExportApi.getSyncTask(taskId)
          const task = taskRes.data
          if (task.status === 'pending' || task.status === 'running') {
            setTimeout(pollTask, 2000)
            return
          }
          // 任务完成
          const ts = new Date().toLocaleString()
          const syncResult: any = {
            synced: task.synced_count ?? 0,
            created: task.created_count ?? 0,
            updated: task.updated_count ?? 0,
            errors: task.failed_count ? [task.message || ''] : [],
            timestamp: ts,
          }
          setSyncResults(prev => ({ ...prev, [type]: syncResult }))
          
          let success = false
          if (task.status === 'failed') {
            message.error(`${getLabel(type)} 同步失败: ${task.message}`)
            success = false
          } else if (task.failed_count > 0) {
            message.warning(`${getLabel(type)} 同步完成，但有 ${task.failed_count} 条错误`)
            success = true
          } else {
            message.success(`${getLabel(type)} 同步完成：新增 ${task.created_count ?? 0}，更新 ${task.updated_count ?? 0}`)
            success = true
          }
          
          // 创建通知
          await createSyncNotification(type, syncResult, success)
          // 显示顶部栏提示
          if (success) {
            antNotification.success({
              message: '同步完成',
              description: `${getLabel(type)} 同步已完成，请查看顶部栏通知`,
              placement: 'topRight',
              duration: 4,
            })
          }
        } catch {
          message.error('查询同步任务状态失败')
        } finally {
          setSyncLoading(prev => ({ ...prev, [type]: false }))
        }
      }
      setTimeout(pollTask, 1500)
    } catch (e: any) {
      const detail = e?.response?.data?.message || e?.response?.data?.detail || e?.message || '同步失败，请检查 ERP 连接和 SQL 配置'
      message.error(detail)
      setSyncLoading(prev => ({ ...prev, [type]: false }))
    }
  }

  const handleSyncAll = async () => {
    setSyncAllLoading(true)
    try {
      // 使用 /sync/all 一次性提交全量同步
      const params: any = { hours }
      const res: any = await importExportApi.syncData('all', params)
      const taskId = res.data?.task_id
      if (!taskId) {
        message.error('同步任务提交失败')
        setSyncAllLoading(false)
        return
      }
      message.info('全量同步任务已提交...')
      const allTypes: string[] = Object.keys(configStatus?.types || {})
      allTypes.forEach(t => setSyncLoading(prev => ({ ...prev, [t]: true })))

      const pollTask = async () => {
        try {
          const taskRes: any = await importExportApi.getSyncTask(taskId)
          const task = taskRes.data
          if (task.status === 'pending' || task.status === 'running') {
            setTimeout(pollTask, 3000)
            return
          }
          const ts = new Date().toLocaleString()
          allTypes.forEach(t => {
            setSyncResults(prev => ({ ...prev, [t]: { synced: 0, created: 0, updated: 0, timestamp: ts } }))
            setSyncLoading(prev => ({ ...prev, [t]: false }))
          })
          if (task.status === 'failed') {
            message.error(`全量同步失败: ${task.message}`)
          } else {
            const created = task.created_count ?? 0
            const updated = task.updated_count ?? 0
            const failed = task.failed_count ?? 0
            if (failed > 0) {
              message.warning(`全量同步完成：新增 ${created}，更新 ${updated}，${failed} 条错误`)
            } else {
              message.success(`全量同步完成：新增 ${created}，更新 ${updated}`)
            }
          }
        } catch {
          message.error('查询同步任务状态失败')
          allTypes.forEach(t => setSyncLoading(prev => ({ ...prev, [t]: false })))
        } finally {
          setSyncAllLoading(false)
        }
      }
      setTimeout(pollTask, 2000)
    } catch (e: any) {
      const detail = e?.response?.data?.message || e?.response?.data?.detail || e?.message || '全量同步失败'
      message.error(detail)
      setSyncAllLoading(false)
    }
  }

  const downloadTemplate = (type: SyncType) => {
    const templates: Record<string, string[][]> = {
      orders: [
        ['order_no', 'line_no', 'customer', 'product_code', 'product_name', 'order_qty', 'promised_date', 'planned_start_date', 'owner'],
        ['ORD-2026-001', '1', 'Customer A', 'P001', 'Product A', '100', '2026-05-01', '2026-04-20', 'planner01'],
      ],
      materials: [
        ['order_no', 'line_no', 'material_code', 'material_name', 'req_qty', 'req_date'],
        ['ORD-2026-001', '1', 'M001', 'Material A', '50', '2026-04-15'],
      ],
      'purchase_orders': [
        ['po_no', 'material_code', 'supplier_code', 'supplier_name', 'po_qty', 'po_status', 'eta', 'original_eta', 'owner'],
        ['PO-2026-001', 'M001', 'S001', 'Supplier A', '50', 'placed', '2026-05-01', '2026-05-01', 'buyer01'],
      ],
    }
    const csvContent = templates[type].map(row => row.join(',')).join('\n')
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `${type}_template.csv`
    link.click()
  }

  const uploadProps = (type: SyncType) => ({
    accept: '.xlsx,.xls,.csv',
    showUploadList: false,
    beforeUpload: (file: File) => handleUpload(file, type),
  })

  // 获取某类型的配置状态
  const getTypeConfig = (type: string) => {
    const key = type
    return configStatus?.types?.[key]
  }

  const renderConfigBadge = (type: string) => {
    const cfg = getTypeConfig(type)
    if (!cfg) return null
    if (!cfg.configured) {
      return (
        <Alert
          type="warning" showIcon icon={<WarningOutlined />}
          message="未配置同步 SQL"
          description="请先到 系统设置 → 同步SQL 中配置此类型的查询语句和字段映射"
          style={{ marginBottom: 12 }}
        />
      )
    }
    if (!cfg.is_active) {
      return (
        <Alert
          type="info" showIcon icon={<InfoCircleOutlined />}
          message="同步配置已禁用"
          description="该同步类型的 SQL 配置当前处于禁用状态"
          style={{ marginBottom: 12 }}
        />
      )
    }
    return null
  }

  const renderSyncCard = (type: SyncType, title: string) => {
    const cfg = getTypeConfig(type)
    const canSync = cfg?.configured && cfg?.is_active
    const result = syncResults[type]
    const isOrders = type === 'orders'
    const isMaterials = type === 'materials'

    return (
      <Card size="small" title={title} extra={
        cfg?.configured ? (
          <Space size={4}>
            {cfg.has_sql && <Tooltip title="SQL 已配置"><CheckCircleOutlined style={{ color: '#52c41a' }} /></Tooltip>}
            {cfg.has_mapping ? (
              <Tooltip title="字段映射已配置"><CheckCircleOutlined style={{ color: '#52c41a' }} /></Tooltip>
            ) : (
              <Tooltip title="字段映射未配置"><WarningOutlined style={{ color: '#faad14' }} /></Tooltip>
            )}
          </Space>
        ) : null
      }>
        {renderConfigBadge(type)}
        {(isOrders || isMaterials) && (
          <div style={{ marginBottom: 12, padding: 12, background: '#f8fafc', borderRadius: 6 }}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 13, fontWeight: 500, color: '#475569' }}>订单选择</span>
                {selectedOrders.length > 0 && (
                  <Button
                    type="link"
                    size="small"
                    onClick={() => setSelectedOrders([])}
                    style={{ padding: 0, fontSize: 12 }}
                  >
                    清空选择
                  </Button>
                )}
              </div>
              <Space>
                <Button
                  icon={<PlusOutlined />}
                  onClick={handleOpenOrderModal}
                  size="small"
                >
                  选择订单
                </Button>
                {selectedOrders.length > 0 && (
                  <Tag color="blue">已选 {selectedOrders.length} 个订单</Tag>
                )}
              </Space>
              <div style={{ fontSize: 12, color: '#64748b' }}>
                提示：选择订单后，将只同步这些订单，忽略时间范围设置
              </div>
            </Space>
          </div>
        )}
        <Space>
          <Button
            type="primary"
            icon={<SyncOutlined spin={syncLoading[type]} />}
            loading={syncLoading[type]}
            disabled={!canSync || syncAllLoading}
            onClick={() => handleSync(type)}
          >
            {(isOrders || isMaterials) && selectedOrders.length > 0 ? '同步选中订单' : '从 ERP 同步'}
          </Button>
          {!canSync && cfg?.configured === false && (
            <span style={{ color: '#94a3b8', fontSize: 12 }}>需先配置同步SQL</span>
          )}
        </Space>
        {result && (
          <div style={{ marginTop: 12 }}>
            <div style={{ marginBottom: 8, fontSize: 12, color: '#64748b' }}>
              <ClockCircleOutlined /> 同步时间: {result.timestamp}
            </div>
            <SyncResultCard result={result} type={type} label={getLabel(type)} />
          </div>
        )}
      </Card>
    )
  }

  // 当前选中类型的配置
  const selectedCfg = selectedType ? configStatus?.types?.[selectedType] : null
  const selectedAlert = selectedType ? TYPE_ALERTS[selectedType] : null
  const selectedExcelFields = selectedType ? EXCEL_IMPORT_TYPES[selectedType] : null

  return (
    <div>
      <div className="filter-bar" style={{ marginBottom: 14 }}>
        <div className="filter-left">
          <Tooltip title="同步最近 N 小时内在 ERP 中更新过的数据">
            <span style={{ fontSize: 13, color: '#64748b' }}>时间范围:</span>
          </Tooltip>
          <InputNumber
            min={1} max={720} value={hours}
            onChange={v => setHours(v ?? 24)}
            addonAfter="小时"
            style={{ width: 140 }}
          />
        </div>
        <div className="filter-right">
          <Button
            type="primary"
            icon={<SyncOutlined spin={syncAllLoading} />}
            loading={syncAllLoading}
            onClick={handleSyncAll}
          >
            一键同步所有数据
          </Button>
          <Button icon={<DownloadOutlined />} onClick={handleExportWeekly}>
            导出周报
          </Button>
        </div>
      </div>

      {/* 全局状态提示 */}
      {configStatus && !configStatus.enabled && (
        <Alert
          type="warning" showIcon
          message="ERP 同步未启用"
          description="请在 .env 中设置 ERP_SYNC_ENABLED=true 并重启服务"
          style={{ marginBottom: 16 }}
        />
      )}
      {configStatus && !configStatus.erp_db_configured && (
        <Alert
          type="error" showIcon
          message="ERP 数据库未配置"
          description="请在 .env 中设置 ERP_DB_URL 连接串并重启服务"
          style={{ marginBottom: 16 }}
        />
      )}

      <Spin spinning={configLoading} tip="加载配置状态...">
        <div className="card-modern" style={{ padding: '20px 24px' }}>
          {/* 数据类型选择 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 13, fontWeight: 500, color: '#475569', whiteSpace: 'nowrap' }}>
              数据类型:
            </span>
            <Select
              value={selectedType || undefined}
              onChange={v => setSelectedType(v)}
              placeholder="选择数据类型"
              showSearch
              optionFilterProp="label"
              style={{ minWidth: 220 }}
              options={Object.entries(configStatus?.types || {}).map(([k, v]) => ({
                value: k,
                label: v.label,
              }))}
            />
            {selectedCfg && (
              <Space size={4}>
                {selectedCfg.has_sql ? (
                  <Tag color="success" style={{ margin: 0 }}><CheckCircleOutlined /> SQL</Tag>
                ) : (
                  <Tag color="warning" style={{ margin: 0 }}><WarningOutlined /> SQL未配置</Tag>
                )}
                {selectedCfg.has_mapping ? (
                  <Tag color="success" style={{ margin: 0 }}><CheckCircleOutlined /> 映射</Tag>
                ) : (
                  <Tag color="default" style={{ margin: 0 }}><WarningOutlined /> 映射未配置</Tag>
                )}
                {!selectedCfg.is_active && (
                  <Tag color="error" style={{ margin: 0 }}>已禁用</Tag>
                )}
              </Space>
            )}
          </div>

          {/* 选中类型的内容 */}
          {selectedType && selectedCfg ? (
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              {selectedAlert && (
                <Alert
                  type="info" showIcon icon={<InfoCircleOutlined />}
                  message={selectedAlert.message}
                  description={selectedAlert.description}
                  style={{ marginBottom: 0 }}
                />
              )}
              {renderSyncCard(selectedType, 'ERP 同步')}
              {selectedExcelFields && (
                <Card size="small" title="Excel 导入（备份）">
                  <p style={{ color: '#94a3b8', fontSize: 11, marginBottom: 12 }}>
                    必填字段: {selectedExcelFields}
                  </p>
                  <Space>
                    <Upload {...uploadProps(selectedType)}>
                      <Button icon={<UploadOutlined />}>选择 Excel/CSV 文件</Button>
                    </Upload>
                    <Button icon={<FileExcelOutlined />} onClick={() => downloadTemplate(selectedType)}>下载模板</Button>
                  </Space>
                </Card>
              )}
            </Space>
          ) : (
            !configLoading && (
              <div style={{ textAlign: 'center', padding: '40px 0', color: '#94a3b8' }}>
                {configStatus && Object.keys(configStatus.types).length === 0
                  ? '暂无已配置的同步类型，请先到「同步SQL配置」中添加'
                  : '请选择数据类型'}
              </div>
            )
          )}
        </div>
      </Spin>

      {importResult && (
        <div className="card-modern mt-4" style={{ padding: '20px 24px' }}>
          <h3 className="text-sm font-semibold mb-3" style={{ color: '#475569' }}>
            导入结果 - <Tag color="blue">{getLabel(importResult.type)}</Tag>
          </h3>
          <Space direction="vertical" size="small" style={{ width: '100%' }}>
            <div>
              <Tag color="green">新增: {importResult.created ?? 0}</Tag>
              <Tag color="orange">更新: {importResult.updated ?? 0}</Tag>
              <Tag color="red">错误: {importResult.errors?.length ?? 0}</Tag>
            </div>
            {importResult.errors?.length > 0 && (
              <Alert
                type="warning"
                message={`${importResult.errors.length} 个验证错误`}
                description={
                  <List
                    size="small"
                    dataSource={importResult.errors.slice(0, 10)}
                    renderItem={(item: string) => <List.Item>{item}</List.Item>}
                  />
                }
              />
            )}
          </Space>
        </div>
      )}

      {/* ============ 同步日志 ============ */}
      <div className="card-modern mt-4" style={{ padding: '20px 24px' }}>
        <div className="flex justify-between items-center mb-3">
          <div className="flex items-center gap-2">
            <HistoryOutlined style={{ color: '#64748b' }} />
            <h4 className="font-semibold m-0" style={{ color: '#334155', fontSize: 14 }}>同步日志</h4>
          </div>
          <Space>
            <Select
              size="small"
              allowClear
              placeholder="筛选类型"
              value={syncLogFilter || undefined}
              onChange={v => setSyncLogFilter(v || '')}
              style={{ width: 140 }}
              options={Object.entries(configStatus?.types || {}).map(([k, v]) => ({ value: k, label: v.label }))}
            />
            <Button size="small" icon={<ReloadOutlined />} onClick={fetchSyncLogs} loading={syncLogsLoading}>刷新</Button>
          </Space>
        </div>
        <Table
          dataSource={syncLogs}
          rowKey="task_id"
          loading={syncLogsLoading}
          size="small"
          scroll={{ y: 260 }}
          pagination={{ pageSize: 10, size: 'small' }}
          columns={[
            {
              title: '类型', dataIndex: 'sync_type', width: 100,
              render: (v: string) => <Tag color="blue" style={{ fontSize: 11 }}>{getLabel(v)}</Tag>,
            },
            {
              title: '触发', dataIndex: 'trigger_mode', width: 70,
              render: (v: string) => <Tag color={v === 'manual' ? 'orange' : 'purple'} style={{ fontSize: 11 }}>{v === 'manual' ? '手动' : '定时'}</Tag>,
            },
            {
              title: '状态', dataIndex: 'status', width: 80,
              render: (v: string) => {
                const map: Record<string, { color: string; label: string }> = {
                  pending: { color: 'default', label: '等待' },
                  running: { color: 'processing', label: '运行中' },
                  success: { color: 'success', label: '成功' },
                  failed: { color: 'error', label: '失败' },
                }
                const item = map[v] || { color: 'default', label: v }
                return <Tag color={item.color} style={{ fontSize: 11 }}>{item.label}</Tag>
              },
            },
            {
              title: '结果', dataIndex: 'message', ellipsis: true,
              render: (v: string) => <span style={{ fontSize: 11, color: '#475569' }}>{v || '-'}</span>,
            },
            {
              title: '耗时', dataIndex: 'duration_seconds', width: 70,
              render: (v: number | null) => v != null ? <span style={{ fontSize: 11 }}>{v.toFixed(1)}s</span> : '-',
            },
            {
              title: '创建时间', dataIndex: 'created_at', width: 140,
              render: (v: string) => v ? <span style={{ fontSize: 11 }}>{new Date(v).toLocaleString('zh-CN')}</span> : '-',
            },
          ]}
        />
      </div>

      {/* 订单选择弹窗 */}
      <Modal
        title="选择订单"
        open={orderModalVisible}
        onCancel={() => setOrderModalVisible(false)}
        width={1000}
        footer={[
          <Button key="cancel" onClick={() => setOrderModalVisible(false)}>
            取消
          </Button>,
          <Button
            key="clear"
            type="default"
            onClick={handleClearOrderSelection}
          >
            清空选择
          </Button>,
          <Button
            key="confirm"
            type="primary"
            onClick={handleConfirmOrderSelection}
            disabled={selectedRowKeys.length === 0}
          >
            确认选择 ({selectedRowKeys.length})
          </Button>,
        ]}
      >
        <Table
          rowKey={(record) => `${record.order_no}-${record.line_no}`}
          columns={[
            { title: '订单号', dataIndex: 'order_no', key: 'order_no', width: 120 },
            { title: '行号', dataIndex: 'line_no', key: 'line_no', width: 70 },
            { title: '客户', dataIndex: 'customer', key: 'customer', ellipsis: true },
            { title: '产品', dataIndex: 'product_name', key: 'product_name', ellipsis: true },
            { title: '承诺交期', dataIndex: 'promised_date', key: 'promised_date', width: 110 },
            { title: '计划上线', dataIndex: 'planned_start_date', key: 'planned_start_date', width: 110 },
          ]}
          dataSource={ordersData}
          loading={ordersLoading}
          rowSelection={{
            selectedRowKeys,
            onChange: setSelectedRowKeys,
          }}
          pagination={{ pageSize: 10 }}
          scroll={{ y: 400 }}
          size="middle"
        />
      </Modal>
    </div>
  )
}
