# URL 搜索参数功能说明

## 功能概述
当用户从 AI 智能助手的搜索结果卡片点击"查看"按钮时，会自动跳转到对应页面，并将关键信息（如订单号、物料编码等）自动填入页面的搜索框，方便用户快速定位。

## 实现方式

### 1. SearchResultListCard 组件（已实现）
在 `frontend/src/components/Assistant/SearchResultListCard.tsx` 中，点击"查看"按钮时会：
- 从标题中提取关键信息（订单号、物料编码等）
- 将关键信息作为 `search` 参数添加到 URL 中
- 跳转到目标页面

```typescript
const handleItemClick = (item: SearchResultItem) => {
  if (item.url) {
    const searchParams = new URLSearchParams();
    
    // 提取订单号格式：HJ202604-0018-0086
    const orderMatch = item.title.match(/[A-Z]{2}\d{6}-\d{4}-\d{4}/);
    // 提取物料编码格式：8位数字
    const materialMatch = item.title.match(/\d{8}/);
    
    if (orderMatch) {
      searchParams.set('search', orderMatch[0]);
    } else if (materialMatch) {
      searchParams.set('search', materialMatch[0]);
    } else {
      searchParams.set('search', item.title);
    }
    
    const url = searchParams.toString() 
      ? `${item.url}?${searchParams.toString()}`
      : item.url;
    
    navigate(url);
  }
};
```

### 2. 目标页面实现（以订单列表为例）

#### 步骤 1：导入 useSearchParams
```typescript
import { useNavigate, useSearchParams } from 'react-router-dom'
```

#### 步骤 2：在组件中添加 URL 参数处理
```typescript
export default function OrderList() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  
  // ... 其他状态定义 ...
  
  // URL 参数处理
  useEffect(() => {
    const searchKeyword = searchParams.get('search')
    if (searchKeyword) {
      // 自动填充搜索关键字到 filters
      setFilters(prev => ({ ...prev, keyword: searchKeyword }))
      
      // 清除 URL 参数，避免刷新页面时重复搜索
      const newParams = new URLSearchParams(searchParams)
      newParams.delete('search')
      setSearchParams(newParams, { replace: true })
    }
  }, [searchParams, setSearchParams])
  
  // ... 其他逻辑 ...
}
```

## 需要添加此功能的页面

以下页面需要添加 URL 参数支持：

### 订单交付中心
- [x] `/orders` - 订单总控台（已实现）
- [ ] `/run-orders` - 跑单管理
- [ ] `/order-risk-pool` - 订单风险池

### 物料齐套中心
- [ ] `/purchase-plan` - 采购到料计划
- [ ] `/material-issues` - 问题物料池
- [ ] `/long-lead-materials` - 长交期物料池
- [ ] `/kit-analysis` - 齐套分析
- [ ] `/supplier-risk` - 供应商风险分析
- [ ] `/supplier-payment` - 供应商付款排程

### 生产协同中心
- [ ] `/production-overview` - 生产总览
- [ ] `/front-process` - 前道管理
- [ ] `/smt` - 贴片管理
- [ ] `/lean` - 精益管理
- [ ] `/assembly` - 组装管理
- [ ] `/packaging` - 包装管理
- [ ] `/process-exceptions` - 工序异常池

### 异常与质量中心
- [ ] `/issues` - 异常总池
- [ ] `/issue-log` - 问题日志
- [ ] `/change-log` - 变更日志
- [ ] `/quality-issues` - 品质异常
- [ ] `/closure-tracking` - 闭环跟踪

### 主数据与集成中心
- [ ] `/users` - 用户管理
- [ ] `/masterdata/*` - 各类主数据管理页面

## 注意事项

1. **参数名称统一**：所有页面都使用 `search` 作为 URL 参数名
2. **自动清除参数**：读取参数后立即清除，避免刷新页面时重复触发
3. **使用 replace 模式**：清除参数时使用 `{ replace: true }`，不在浏览器历史中留下记录
4. **适配不同搜索字段**：根据页面的实际搜索字段名称（如 `keyword`、`search`、`filter` 等）进行适配

## 扩展建议

如果需要传递更复杂的参数（如日期范围、多个筛选条件等），可以扩展 URL 参数：

```typescript
// 传递多个参数
searchParams.set('search', orderNo)
searchParams.set('status', 'open')
searchParams.set('risk_level', 'red')

// 在目标页面读取
const searchKeyword = searchParams.get('search')
const status = searchParams.get('status')
const riskLevel = searchParams.get('risk_level')
```
