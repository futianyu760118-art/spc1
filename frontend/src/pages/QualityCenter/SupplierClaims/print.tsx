import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button, Card, Spin } from 'antd'
import { ArrowLeftOutlined, PrinterOutlined } from '@ant-design/icons'
import { qualityApi } from '../../../services/quality'
import ClaimPaper, { opinionsFromClaim } from '../../../components/ClaimPaper'

export default function SupplierClaimPrint() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [r, setR] = useState<any>(null)

  useEffect(() => {
    ;(async () => {
      try {
        const res: any = await qualityApi.get(parseInt(id!))
        setR(res.data)
      } catch { /* 全局拦截器已提示 */ }
    })()
  }, [id])

  if (!r) return <div className="sc-page clm-print"><Card styles={{ body: { padding: 60 } }}><Spin /></Card></div>

  return (
    <div className="sc-page clm-print">
      <div className="clm-no-print" style={{ maxWidth: 900, margin: '0 auto 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(`/quality/supplier-claims/${r.id}`)}>返回详情</Button>
        <span className="sc-note">
          供应商索赔通知单 <b className="sc-mono" style={{ color: '#0f172a' }}>{r.claim_no}</b>
          {' · '}{r.approval_status === 'approved' ? '已归档版式（各级签字已填充）' : '归档前预览（意见区随审批进度填充）'}
        </span>
        <Button type="primary" icon={<PrinterOutlined />} style={{ marginLeft: 'auto' }} onClick={() => window.print()}>
          打印 / 另存为 PDF
        </Button>
      </div>

      <div className="clm-sheet">
        <div className="clm-paper-wrap"><ClaimPaper claim={r} opinions={opinionsFromClaim(r)} /></div>
      </div>

      <div className="clm-no-print sc-note" style={{ textAlign: 'center', margin: '14px auto 0' }}>
        浏览器打印对话框 → 目标选择「另存为 PDF」· 纸张 A4 · 边距默认
      </div>
    </div>
  )
}
