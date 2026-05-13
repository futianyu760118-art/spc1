import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#6366f1',
          borderRadius: 10,
          colorBgContainer: 'rgba(255,255,255,.55)',
        },
        components: {
          Button: { borderRadius: 10 },
          Input: { borderRadius: 10 },
          Select: { borderRadius: 10 },
          Table: { borderRadiusLG: 12 },
          Modal: { borderRadiusLG: 16 },
          Card: { borderRadiusLG: 16 },
        },
      }}
    >
      <App />
    </ConfigProvider>
  </React.StrictMode>,
)
