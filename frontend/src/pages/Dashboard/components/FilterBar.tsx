import { Input, Select, Space, Segmented, DatePicker, Switch } from 'antd'
import { AppstoreOutlined, ShoppingCartOutlined, ExperimentOutlined } from '@ant-design/icons'

interface FilterBarProps {
  viewMode: 'management' | 'purchasing' | 'material'
  onViewChange: (mode: 'management' | 'purchasing' | 'material') => void
  onSearch: (keyword: string) => void
  onRiskChange: (level: string) => void
  onOwnerChange?: (owner: string) => void
  onDateChange?: (dates: [string, string] | null) => void
  onDataSourceChange?: (source: string) => void
  onShortageOnly?: (v: boolean) => void
}

export default function FilterBar({ viewMode, onViewChange, onSearch, onRiskChange, onOwnerChange, onDateChange, onDataSourceChange, onShortageOnly }: FilterBarProps) {
  const placeholders: Record<string, string> = {
    management: '搜索订单号 / 客户 / 物料',
    purchasing: '搜索 PO号 / 供应商 / 物料',
    material: '搜索物料编码 / 名称 / 订单号',
  }
  return (
    <div className="filter-bar" style={{ marginBottom: 14 }}>
      <div className="flex items-center justify-between flex-wrap gap-3">
        <Space size="middle" wrap>
          <Input.Search
            placeholder={placeholders[viewMode]}
            allowClear
            onSearch={onSearch}
            style={{ width: 280 }}
          />
          {viewMode === 'management' && (
            <Select
              placeholder="风险等级"
              allowClear
              style={{ width: 120 }}
              onChange={(v) => onRiskChange(v || '')}
              options={[
                { value: 'red', label: '高风险' },
                { value: 'yellow', label: '中风险' },
                { value: 'green', label: '正常' },
              ]}
            />
          )}
          {viewMode === 'material' && (
            <Space>
              <span style={{ fontSize: 12, color: '#64748b' }}>仅欠料</span>
              <Switch size="small" onChange={(v) => onShortageOnly?.(v)} />
            </Space>
          )}
          <Select
            placeholder="数据来源"
            allowClear
            style={{ width: 120 }}
            onChange={(v) => onDataSourceChange?.(v || '')}
            options={[
              { value: 'erp', label: 'ERP' },
              { value: 'srm', label: 'SRM' },
              { value: 'excel', label: 'Excel' },
              { value: 'manual', label: '手动' },
            ]}
          />
          <Input
            placeholder="责任人"
            allowClear
            style={{ width: 120 }}
            onChange={(e) => onOwnerChange?.(e.target.value)}
          />
          <DatePicker.RangePicker
            placeholder={['开始日期', '结束日期']}
            style={{ width: 240 }}
            onChange={(_, dateStrings) => {
              onDateChange?.(dateStrings[0] ? [dateStrings[0], dateStrings[1]] : null)
            }}
          />
        </Space>
        <Segmented
          value={viewMode}
          onChange={(v) => onViewChange(v as 'management' | 'purchasing' | 'material')}
          options={[
            { value: 'management', label: '管理视图', icon: <AppstoreOutlined /> },
            { value: 'purchasing', label: '采购视图', icon: <ShoppingCartOutlined /> },
            { value: 'material', label: '物料视图', icon: <ExperimentOutlined /> },
          ]}
        />
      </div>
    </div>
  )
}
