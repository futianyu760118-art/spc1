import { Button, Input, InputNumber, Segmented, Select } from 'antd'
import { ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import type { ApprovalCondition, ApprovalNodeConfig, ApprovalUserOption } from '../services/approval'

// 与后端 approval_metrics.DEFAULT_TIMEOUT_HOURS 对齐：未配置超时的节点按 48 小时提醒
const DEFAULT_TIMEOUT_HOURS = 48

const OP_OPTIONS = [
  { value: '>=', label: '≥ 大于等于' },
  { value: '<=', label: '≤ 小于等于' },
  { value: '>', label: '> 大于' },
  { value: '<', label: '< 小于' },
  { value: '==', label: '= 等于' },
  { value: '!=', label: '≠ 不等于' },
  { value: 'in', label: 'in 属于（逗号分隔）' },
]

const APPROVER_MODE_OPTIONS = [
  { value: 'role', label: '按角色' },
  { value: 'users', label: '指定人员' },
]

export default function ApprovalChainEditor({ nodes, onChange, roleOptions, userOptions, fieldOptions, paperSlotOptions }: {
  nodes: ApprovalNodeConfig[]
  onChange: (nodes: ApprovalNodeConfig[]) => void
  roleOptions: { value: string; label: string }[]
  userOptions: ApprovalUserOption[]
  fieldOptions: Array<{ value: string; label: string }>
  paperSlotOptions?: Array<{ value: string; label: string }>
}) {
  const userLabel = (username?: string, userId?: number) => {
    const hit = userOptions.find(u => u.username === username || u.id === userId)
    return hit ? `${hit.display_name || hit.username}（${hit.username}）` : username || String(userId ?? '')
  }
  const roleLabel = (v?: string) => roleOptions.find(o => o.value === v)?.label || v || '-'
  const fieldLabel = (v: string) => fieldOptions.find(o => o.value === v)?.label || v

  const condsOf = (node: ApprovalNodeConfig): ApprovalCondition[] =>
    node.conditions?.length ? node.conditions : (node.condition ? [node.condition] : [])

  const condText = (c: ApprovalCondition) => {
    const op = OP_OPTIONS.find(o => o.value === c.op)?.label?.split(' ')[0] || c.op
    const val = Array.isArray(c.value) ? c.value.join(', ') : c.value
    return `${fieldLabel(c.field)} ${op} ${val}`
  }

  const condValueText = (c: ApprovalCondition) => (Array.isArray(c.value) ? c.value.join(',') : String(c.value ?? ''))

  const approverText = (node: ApprovalNodeConfig) => node.approvers?.length
    ? node.approvers.map(a => userLabel(a.username, a.user_id)).join('、')
    : (node.role ? roleLabel(node.role) : '未指定审批人')

  const timeoutText = (node: ApprovalNodeConfig) => {
    if (node.timeout_hours) return `${node.timeout_hours}h`
    return node.timeout_hours === 0 ? '不提醒' : `${DEFAULT_TIMEOUT_HOURS}h（默认）`
  }

  const patchNode = (index: number, patch: Partial<ApprovalNodeConfig>) =>
    onChange(nodes.map((n, i) => (i === index ? { ...n, ...patch } : n)))

  // 空数组会被后端判为「触发条件为空」，须整体删键；历史单条件 condition 一并清理，避免双份数据
  const setConditions = (index: number, conds: ApprovalCondition[]) =>
    patchNode(index, conds.length
      ? { conditions: conds, condition: undefined }
      : { conditions: undefined, condition: undefined })

  const addCondition = (index: number) =>
    setConditions(index, [...condsOf(nodes[index]), { field: fieldOptions[0]?.value || '', op: '>=', value: '' }])

  const updateCondition = (index: number, condIndex: number, patch: Partial<ApprovalCondition>) =>
    setConditions(index, condsOf(nodes[index]).map((c, ci) => (ci === condIndex ? { ...c, ...patch } : c)))

  const removeCondition = (index: number, condIndex: number) =>
    setConditions(index, condsOf(nodes[index]).filter((_, ci) => ci !== condIndex))

  const setApproverMode = (index: number, mode: 'role' | 'users') =>
    patchNode(index, mode === 'users' ? { approvers: [] } : { approvers: undefined })

  const setApprovers = (index: number, ids: number[]) =>
    patchNode(index, { approvers: ids.map(id => ({ user_id: id, username: userOptions.find(u => u.id === id)?.username })) })

  const addNode = () => onChange([
    ...nodes,
    { label: `节点 ${nodes.length + 1}`, role: '', timeout_hours: DEFAULT_TIMEOUT_HOURS },
  ].map((n, i) => ({ ...n, seq: i + 1 })))

  const removeNode = (index: number) =>
    onChange(nodes.filter((_, i) => i !== index).map((n, i) => ({ ...n, seq: i + 1 })))

  const move = (index: number, dir: -1 | 1) => {
    const target = index + dir
    if (target < 0 || target >= nodes.length) return
    const next = [...nodes]
    ;[next[index], next[target]] = [next[target], next[index]]
    onChange(next.map((n, i) => ({ ...n, seq: i + 1 })))
  }

  return (
    <div>
      <div className="ac-sec-title">链预览 · 按顺序执行，条件不满足的节点自动跳过</div>
      {nodes.length === 0 ? (
        <div className="ac-node-card" style={{ padding: '14px 12px', textAlign: 'center' }}>
          <span className="sc-note">暂无节点，保存会被拒绝</span>
        </div>
      ) : (
        <div className="ac-node-flow">
          {nodes.map((node, i) => (
            <div key={i} className="ac-node">
              <div className="nd-dot">{i + 1}</div>
              <div className="nd-name" title={node.label}>{node.label || '未命名节点'}</div>
              <div className="nd-date">
                <div>{approverText(node)}</div>
                {condsOf(node).map((c, ci) => <div key={ci}>{condText(c)}</div>)}
                <div><b>超时</b> {timeoutText(node)}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="ac-sec-title gap">节点列表 · 可调整顺序与审批人</div>
      {nodes.map((node, index) => {
        const conds = condsOf(node)
        // 用键是否存在而非长度推导：切到「指定人员」的瞬间 approvers 为空数组，按长度推导会立刻弹回「按角色」
        const useUsers = Array.isArray(node.approvers)
        return (
          <div key={index} className="ac-node-card">
            <div className="ac-nc-head">
              <span className="ac-nc-seq">{index + 1}</span>
              <div className="ac-nc-name">
                <Input variant="borderless" value={node.label} placeholder="节点名称" maxLength={32}
                  onChange={e => patchNode(index, { label: e.target.value })} />
              </div>
              <div className="ac-nc-tools">
                <Button type="text" size="small" title="上移" icon={<ArrowUpOutlined />} disabled={index === 0} onClick={() => move(index, -1)} />
                <Button type="text" size="small" title="下移" icon={<ArrowDownOutlined />} disabled={index === nodes.length - 1} onClick={() => move(index, 1)} />
                <Button type="text" size="small" danger className="danger" title="删除" icon={<DeleteOutlined />} onClick={() => removeNode(index)} />
              </div>
            </div>
            <div className="ac-nc-body">
              <div className="ac-nc-field">
                <label>审批人</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Segmented options={APPROVER_MODE_OPTIONS} value={useUsers ? 'users' : 'role'}
                    onChange={v => setApproverMode(index, v as 'role' | 'users')} />
                  {useUsers ? (
                    <Select mode="multiple" showSearch optionFilterProp="label" placeholder="搜索姓名 / 用户名"
                      style={{ flex: 1, minWidth: 0 }}
                      value={(node.approvers || []).map(a => a.user_id).filter((id): id is number => typeof id === 'number')}
                      options={userOptions.map(u => ({ value: u.id, label: `${u.display_name || u.username}（${u.username}${u.role_name ? ' · ' + u.role_name : ''}）` }))}
                      onChange={ids => setApprovers(index, ids)} />
                  ) : (
                    <Select options={roleOptions} value={node.role || undefined} placeholder="选择审批角色"
                      style={{ flex: 1, minWidth: 0 }}
                      onChange={v => patchNode(index, { role: v, approvers: undefined })} />
                  )}
                </div>
              </div>
              {paperSlotOptions?.length ? (
                <div className="ac-nc-field">
                  <label>纸质签字区</label>
                  <Select allowClear options={paperSlotOptions} value={node.paper_slot || undefined}
                    placeholder="不绑定（按名称/角色自动匹配）" style={{ width: '100%' }}
                    onChange={v => patchNode(index, { paper_slot: v || undefined })} />
                </div>
              ) : null}
              <div className="ac-nc-field">
                <label>超时提醒（小时，0 = 不提醒）</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <InputNumber min={0} max={720} precision={0} style={{ width: 96 }}
                    placeholder={String(DEFAULT_TIMEOUT_HOURS)} value={node.timeout_hours ?? undefined}
                    onChange={v => patchNode(index, { timeout_hours: v ?? null })} />
                  <span className="ac-nc-hint">到达阈值推送站内信 + 企微，同节点 24h 去重</span>
                </div>
              </div>
              <div className="ac-nc-field full">
                <label>触发条件（全部满足才进入本节点，留空 = 无条件）</label>
                {conds.length === 0 ? <div className="ac-nc-hint" style={{ marginBottom: 6 }}>无条件：任何情况都会进入本节点</div> : null}
                {conds.map((c, ci) => (
                  <div key={ci} className="ac-cond-row">
                    <Select className="field" options={fieldOptions} value={c.field || undefined} placeholder="条件字段"
                      onChange={v => updateCondition(index, ci, { field: v })} />
                    <Select className="op" options={OP_OPTIONS} value={c.op}
                      onChange={v => updateCondition(index, ci, { op: v as ApprovalCondition['op'] })} />
                    <Input className="val" placeholder="阈值 / 逗号分隔" value={condValueText(c)}
                      onChange={e => updateCondition(index, ci, { value: e.target.value })} />
                    <span className="rm" title="删除条件" onClick={() => removeCondition(index, ci)}>×</span>
                  </div>
                ))}
                <span className="ac-cond-add" onClick={() => addCondition(index)}>
                  <PlusOutlined className="ac-ico-sm" />添加条件
                </span>
              </div>
            </div>
          </div>
        )
      })}
      <div className="ac-add-node" onClick={addNode}>
        <PlusOutlined className="ac-ico-md" />添加节点
      </div>
    </div>
  )
}
