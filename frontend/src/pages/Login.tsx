import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Form, Input, Button, message } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { authApi } from '../services/api'
import { useAuthStore } from '../store/auth'

export default function Login() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      const res: any = await authApi.login(values.username, values.password)
      const token = res.data.access_token

      useAuthStore.getState().setAuth(token, null)
      const meRes: any = await authApi.getMe()
      setAuth(token, meRes.data)
      message.success('登录成功')
      navigate('/dashboard')
    } catch {
      message.error('登录失败，请检查用户名和密码')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-bg">
      <div className="login-card">
        <div className="text-center mb-8">
          <div
            className="inline-flex items-center justify-center mb-4"
            style={{ width: 48, height: 48, borderRadius: 14, background: 'linear-gradient(135deg, #6366f1, #818cf8)', boxShadow: '0 4px 16px rgba(99,102,241,.25)' }}
          >
            <LockOutlined style={{ fontSize: 22, color: '#fff' }} />
          </div>
          <h1 className="text-xl font-bold m-0" style={{ color: '#0f172a' }}>
            供应链与生产协同中台
          </h1>
          <p className="mt-2" style={{ color: '#94a3b8', fontSize: 13 }}>
            Supply Chain & Production Collaboration
          </p>
        </div>

        <Form onFinish={onFinish} autoComplete="off" size="large">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input
              prefix={<UserOutlined style={{ color: '#a5b4fc' }} />}
              placeholder="用户名"
              style={{ background: 'rgba(255,255,255,.5)', borderColor: 'rgba(0,0,0,.08)' }}
            />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password
              prefix={<LockOutlined style={{ color: '#a5b4fc' }} />}
              placeholder="密码"
              style={{ background: 'rgba(255,255,255,.5)', borderColor: 'rgba(0,0,0,.08)' }}
            />
          </Form.Item>
          <Form.Item className="mb-0 mt-2">
            <Button type="primary" htmlType="submit" loading={loading} block size="large"
              style={{ height: 44, fontWeight: 600 }}
            >
              登录
            </Button>
          </Form.Item>
        </Form>
      </div>
    </div>
  )
}
