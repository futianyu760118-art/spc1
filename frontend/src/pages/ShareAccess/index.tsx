import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Result, Button, Spin } from 'antd'
import { shareApi } from '../../services/api'
import { useAuthStore } from '../../store/auth'

export default function ShareAccess() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const setShareAuth = useAuthStore((s) => s.setShareAuth)
  const [error, setError] = useState<string>('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!token) {
      setError('无效的分享链接')
      setLoading(false)
      return
    }

    shareApi
      .verify(token)
      .then((result: any) => {
        const { access_token, target_path, target_params, permissions } = result.data
        // 设置分享认证状态
        setShareAuth(access_token, target_path, permissions)

        // 构建目标路径（含参数）
        let targetUrl = target_path
        if (target_params && typeof target_params === 'object') {
          // 对于订单详情等动态路由，替换路径参数
          // 例如 target_path="/orders/:orderNo/lines/:lineNo", target_params={orderNo:"xxx",lineNo:"1"}
          const pathParams = Object.entries(target_params)
          for (const [key, value] of pathParams) {
            targetUrl = targetUrl.replace(`:${key}`, String(value))
          }
        }

        // 跳转到目标页面
        navigate(targetUrl, { replace: true })
      })
      .catch((e: any) => {
        const detail = e?.response?.data?.detail
        if (detail) {
          setError(detail)
        } else {
          setError(e?.message || '分享链接验证失败')
        }
        setLoading(false)
      })
  }, [token, setShareAuth, navigate])

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" tip="正在验证分享链接..." />
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
      <Result
        status="error"
        title="无法访问"
        subTitle={error}
        extra={[
          <Button type="primary" key="login" onClick={() => navigate('/login')}>
            前往登录
          </Button>,
        ]}
      />
    </div>
  )
}
