import { useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { Form, Input, Button, message } from 'antd'
import { UserOutlined, LockOutlined, ShopOutlined, TeamOutlined } from '@ant-design/icons'
import { authApi } from '../services/api'
import { useAuthStore } from '../store/auth'
import { SUPPLIER_PORTAL_PATHS } from '../constants/permissions'

type LoginType = 'employee' | 'supplier'

interface LoginFormValues {
  loginType: LoginType
  username: string
  password: string
}

const PATH_TO_PERMISSION: Record<string, string> = {
  '/purchase-plan': 'materials.purchase_plan',
  '/long-lead-materials': 'materials.long_lead',
  '/supplier-risk': 'materials.supplier_risk',
  '/supplier-payment': 'materials.supplier_payment',
}

const LOGIN_TYPE_OPTIONS: Array<{
  label: string
  description: string
  value: LoginType
  icon: ReactNode
}> = [
  {
    label: '内部员工',
    description: '企业账号',
    value: 'employee',
    icon: <TeamOutlined />,
  },
  {
    label: '供应商',
    description: '协作账号',
    value: 'supplier',
    icon: <ShopOutlined />,
  },
]

export default function Login() {
  const [form] = Form.useForm<LoginFormValues>()
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)

  const onFinish = async (values: LoginFormValues) => {
    setLoading(true)
    try {
      const res: any = await authApi.login(values.username, values.password, values.loginType)
      const token = res.data.access_token

      useAuthStore.getState().setAuth(token, null)
      const meRes: any = await authApi.getMe()
      const user = meRes.data
      const isSupplierAccount = user?.role_code === 'supplier'
      if (values.loginType === 'supplier' && !isSupplierAccount) {
        useAuthStore.getState().logout()
        message.warning('当前为内部员工账号，请切换到内部员工登录')
        return
      }
      if (values.loginType === 'employee' && isSupplierAccount) {
        useAuthStore.getState().logout()
        message.warning('当前为供应商账号，请切换到供应商登录')
        return
      }

      setAuth(token, user)
      message.success('登录成功')
      if (isSupplierAccount) {
        const firstAllowedPath = SUPPLIER_PORTAL_PATHS.find(path => {
          const permission = PATH_TO_PERMISSION[path]
          return permission && useAuthStore.getState().hasPermission(permission, 'read')
        })
        navigate(firstAllowedPath || '/purchase-plan')
      } else {
        navigate('/dashboard')
      }
    } catch (error: any) {
      message.error(error?.message || '登录失败，请检查用户名和密码')
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

        <Form form={form} onFinish={onFinish} autoComplete="off" size="large" initialValues={{ loginType: 'employee' }}>
          <Form.Item name="loginType" hidden>
            <Input />
          </Form.Item>
          <Form.Item
            className="login-role-field"
            shouldUpdate={(prev, current) => prev.loginType !== current.loginType}
          >
            {({ getFieldValue, setFieldsValue }) => {
              const currentLoginType = (getFieldValue('loginType') || 'employee') as LoginType

              return (
                <div className="login-role-switch" role="radiogroup" aria-label="登录身份">
                  <span
                    className={`login-role-indicator${currentLoginType === 'supplier' ? ' is-supplier' : ''}`}
                    aria-hidden="true"
                  />
                  {LOGIN_TYPE_OPTIONS.map((option) => {
                    const isActive = currentLoginType === option.value

                    return (
                      <button
                        key={option.value}
                        type="button"
                        className={`login-role-option${isActive ? ' is-active' : ''}`}
                        role="radio"
                        aria-checked={isActive}
                        onClick={() => setFieldsValue({ loginType: option.value })}
                      >
                        <span className="login-role-icon">{option.icon}</span>
                        <span className="login-role-text">
                          <span className="login-role-label">{option.label}</span>
                          <span className="login-role-desc">{option.description}</span>
                        </span>
                      </button>
                    )
                  })}
                </div>
              )
            }}
          </Form.Item>
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
