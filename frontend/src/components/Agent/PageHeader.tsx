import React from 'react'

interface Props {
  title: string
  subtitle?: string
  extra?: React.ReactNode
}

export default function PageHeader({ title, subtitle, extra }: Props) {
  return (
    <div className="ai-page-head">
      <div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {extra && <div className="ai-actions">{extra}</div>}
    </div>
  )
}
