import { useEffect, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { Result, Button, Spin } from 'antd'
import { shareApi } from '../../services/api'
import { useAuthStore } from '../../store/auth'

export default function ShareAccess() {
  const { token } = useParams<{ token: string }>()
  const [searchParams] = useSearchParams()
  const code = searchParams.get('code')
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
      .verify(token, code || undefined)
      .then((result: any) => {
        const { access_token, target_path, target_params, permissions } = result.data
        // 设置分享认证状态
        setShareAuth(access_token, target_path, permissions)

        // 构建目标路径（含参数）
        let targetUrl = target_path
        if (target_params && typeof target_params === 'object') {
          // 路径参数(:key)替换；其余参数作为 query string 附加
          const leftover: Record<string, string> = {}
          for (const [key, value] of Object.entries(target_params)) {
            if (targetUrl.includes(`:${key}`)) {
              targetUrl = targetUrl.replace(`:${key}`, String(value))
            } else {
              leftover[key] = String(value)
            }
          }
          const qs = new URLSearchParams(leftover).toString()
          if (qs) {
            targetUrl += (targetUrl.includes('?') ? '&' : '?') + qs
          }
        }

        // 跳转到目标页面
        navigate(targetUrl, { replace: true })
      })
      .catch((e: any) => {
        const detail = e?.response?.data?.detail
        // 限制型分享：需要企微 OAuth 身份验证，重定向到企微授权页
        if (detail && typeof detail === 'object' && detail.oauth_url) {
          window.location.href = detail.oauth_url
          return
        }
        if (typeof detail === 'string') {
          setError(detail)
        } else if (detail?.message) {
          setError(detail.message)
        } else {
          setError(e?.message || '分享链接验证失败')
        }
        setLoading(false)
      })
  }, [token, code, setShareAuth, navigate])

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
