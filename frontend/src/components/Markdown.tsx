import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// 统一的 Markdown 渲染组件（GFM）：AI 助手回复、反馈处理回复共用，保证各处 MD 排版一致。
// 外层容器可叠加 whiteSpace: 'pre-wrap'，使纯文本的单个换行仍按换行显示。
export default function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }: { children?: ReactNode }) => <p style={{ margin: '6px 0' }}>{children}</p>,
        ul: ({ children }: { children?: ReactNode }) => <ul style={{ margin: '6px 0', paddingLeft: '18px' }}>{children}</ul>,
        ol: ({ children }: { children?: ReactNode }) => <ol style={{ margin: '6px 0', paddingLeft: '18px' }}>{children}</ol>,
        li: ({ children }: { children?: ReactNode }) => <li style={{ margin: '3px 0', lineHeight: 1.6 }}>{children}</li>,
        strong: ({ children }: { children?: ReactNode }) => <strong style={{ color: '#1a1a1a' }}>{children}</strong>,
        em: ({ children }: { children?: ReactNode }) => <em>{children}</em>,
        h1: ({ children }: { children?: ReactNode }) => <h4 style={{ margin: '10px 0 6px', fontSize: 14, fontWeight: 600 }}>{children}</h4>,
        h2: ({ children }: { children?: ReactNode }) => <h5 style={{ margin: '8px 0 4px', fontSize: 13, fontWeight: 600 }}>{children}</h5>,
        h3: ({ children }: { children?: ReactNode }) => <h6 style={{ margin: '6px 0 4px', fontSize: 13, fontWeight: 600 }}>{children}</h6>,
        hr: () => <hr style={{ border: 'none', borderTop: '1px solid #e8e8e8', margin: '8px 0' }} />,
        table: ({ children }: { children?: ReactNode }) => (
          <div style={{ overflowX: 'auto', margin: '8px 0' }}>
            <table style={{ borderCollapse: 'collapse', fontSize: 12, width: '100%', minWidth: 280 }}>
              {children}
            </table>
          </div>
        ),
        thead: ({ children }: { children?: ReactNode }) => (
          <thead style={{ background: '#fafafa' }}>{children}</thead>
        ),
        th: ({ children }: { children?: ReactNode }) => (
          <th style={{ border: '1px solid #e8e8e8', padding: '4px 8px', fontWeight: 600, textAlign: 'left', whiteSpace: 'nowrap' }}>
            {children}
          </th>
        ),
        td: ({ children }: { children?: ReactNode }) => (
          <td style={{ border: '1px solid #e8e8e8', padding: '4px 8px', whiteSpace: 'nowrap' }}>
            {children}
          </td>
        ),
        code: ({ children, className }: { children?: ReactNode; className?: string }) => {
          // 区分行内代码和代码块
          const isBlock = className?.startsWith('language-')
          if (isBlock) {
            return (
              <pre style={{ background: '#f6f6f6', padding: '8px 12px', borderRadius: 4, overflow: 'auto', fontSize: 11, margin: '6px 0' }}>
                <code>{children}</code>
              </pre>
            )
          }
          return (
            <code style={{ background: 'rgba(150, 150, 150, 0.15)', padding: '1px 4px', borderRadius: 3, fontSize: 12 }}>
              {children}
            </code>
          )
        },
        blockquote: ({ children }: { children?: ReactNode }) => (
          <blockquote style={{ borderLeft: '3px solid #6366f1', margin: '6px 0', paddingLeft: 10, color: '#555' }}>
            {children}
          </blockquote>
        ),
      }}
    >
      {children}
    </ReactMarkdown>
  )
}
