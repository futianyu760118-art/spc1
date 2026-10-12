import React from 'react'
import {unstable_HistoryRouter as HistoryRouter, Routes, Route, Navigate, useLocation} from 'react-router-dom'
import {App as AntdApp, ConfigProvider, Result} from 'antd'
import MainLayout from './layouts/MainLayout'
import { appHistory } from './utils/appHistory'
import Login from './pages/Login'
import ShareAccess from './pages/ShareAccess'
import {useAuthStore} from './store/auth'
import {useThemeStore} from './store/theme'
import {setGlobalMessageApi} from './utils/antdMessage'
import { contentRoutes } from './router/contentRoutes'

function AntdMessageBridge() {
    const {message} = AntdApp.useApp()

    React.useEffect(() => {
        setGlobalMessageApi(message)
    }, [message])

    return null
}

function PrivateRoute({children}: { children: React.ReactNode }) {
    const token = useAuthStore((s) => s.currentToken)
    const location = useLocation()
    if (!token) return <Navigate to="/login" replace state={{ from: location }}/>
    return <>{children}</>
}

// 检查分享用户是否有权访问当前路径
function ShareRouteGuard({children}: { children: React.ReactNode }) {
    const {isShareUser, getShareTargetPath} = useAuthStore()
    const location = useLocation()

    if (!isShareUser()) return <>{children}</>

    const targetPath = getShareTargetPath()
    if (!targetPath) return <>{children}</>

    const currentPath = location.pathname

    // 动态路由匹配（如 /orders/:orderNo/lines/:lineNo）
    if (targetPath.includes(':')) {
        const prefix = targetPath.split('/:')[0]
        if (currentPath.startsWith(prefix)) return <>{children}</>
    }

    // 精确匹配
    if (currentPath === targetPath) return <>{children}</>

    // 子路径匹配（如 /basicdata/customers 匹配 /basicdata）
    if (currentPath.startsWith(targetPath)) return <>{children}</>

    // 不匹配：显示无权限
    return (
        <div style={{display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh'}}>
            <Result
                status="403"
                title="无访问权限"
                subTitle="您只能访问分享的页面，其他页面无权查看"
            />
        </div>
    )
}

export default function App() {
    const {fontSizeScale} = useThemeStore()

    // Apply font scale to root element
    React.useEffect(() => {
        document.documentElement.style.setProperty('--font-size-scale', fontSizeScale.toString())
    }, [fontSizeScale])

    return (
        <ConfigProvider
            theme={{
                token: {
                    fontSize: 14 * fontSizeScale,
                },
            }}
        >
            <AntdApp>
                <AntdMessageBridge/>
                <HistoryRouter history={appHistory}>
                    <Routes>
                        <Route path="/login" element={<Login/>}/>
                        <Route path="/share/:token" element={<ShareAccess/>}/>
                        <Route
                            path="/"
                            element={
                                <PrivateRoute>
                                    <ShareRouteGuard>
                                        <MainLayout/>
                                    </ShareRouteGuard>
                                </PrivateRoute>
                            }
                        >
                            {contentRoutes}
                        </Route>
                    </Routes>
                </HistoryRouter>
            </AntdApp>
        </ConfigProvider>
    )
}
