import { Card } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../../store/auth'
import { listBusinesses } from './businesses'

export default function ApprovalCreate() {
  const navigate = useNavigate()
  const hasPermission = useAuthStore((s) => s.hasPermission) as (resource: string, action: string) => boolean
  const businesses = listBusinesses().filter(item => hasPermission(item.permission[0], item.permission[1]))

  return (
    <div className="sc-page">
      <Card>
        <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 4 }}>发起申请</div>
        <div className="sc-note" style={{ marginBottom: 16 }}>选择业务类型，填写并提交后进入对应审批链</div>
        {businesses.length === 0 ? (
          <div className="ac-empty">
            <div className="ac-empty-title">暂无可发起的业务</div>
            <div className="ac-empty-sub">请联系管理员开通对应业务的创建权限</div>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 12 }}>
            {businesses.map(item => (
              <Card key={item.bizType} hoverable size="small"
                onClick={() => navigate(`/approvals/create/${item.bizType}`)}>
                <div style={{ fontWeight: 600 }}>{item.name}</div>
                <div className="sc-note" style={{ marginTop: 6 }}>{item.description}</div>
              </Card>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
