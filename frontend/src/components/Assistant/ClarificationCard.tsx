import React, { useMemo, useState } from 'react'
import { Button, Card, Checkbox, Input, Radio, Space, Typography } from 'antd'
import type { ClarificationQuestion, ClarificationSpec } from './clarification'

const { Text } = Typography

interface Props {
  spec: ClarificationSpec
  onSubmit: (answer: string) => void
}

type AnswerValue = string | string[]

export default function ClarificationCard({ spec, onSubmit }: Props) {
  const [values, setValues] = useState<Record<string, AnswerValue>>({})
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState('')

  const optionLabels = useMemo(() => {
    const labels: Record<string, Record<string, string>> = {}
    spec.questions.forEach(question => {
      labels[question.id] = (question.options || []).reduce<Record<string, string>>((acc, option) => {
        acc[option.value] = option.label
        return acc
      }, {})
    })
    return labels
  }, [spec])

  const setValue = (questionId: string, value: AnswerValue) => {
    setValues(prev => ({ ...prev, [questionId]: value }))
    setError('')
  }

  const submit = () => {
    const missing = spec.questions.filter(question => {
      if (question.required === false) return false
      const value = values[question.id]
      if (question.type === 'multiple') return !Array.isArray(value) || value.length === 0
      return typeof value !== 'string' || !value.trim()
    })
    if (missing.length > 0) {
      setError(`请先完成：${missing.map(question => question.label).join('、')}`)
      return
    }
    const lines = spec.questions.map(question => {
      const value = values[question.id]
      const labels = optionLabels[question.id] || {}
      let answer = ''
      if (question.type === 'multiple') {
        answer = (Array.isArray(value) ? value : []).map(item => labels[item] || item).join('、')
      } else if (question.type === 'single') {
        answer = labels[String(value || '')] || String(value || '')
      } else {
        answer = typeof value === 'string' ? value.trim() : ''
      }
      return `- ${question.label}：${answer || '（未填写）'}`
    })
    onSubmit(`我确认以下内容：\n${lines.join('\n')}`)
    setSubmitted(true)
  }

  const renderQuestion = (question: ClarificationQuestion) => {
    if (question.type === 'single') {
      return (
        <Radio.Group
          value={values[question.id] as string | undefined}
          onChange={event => setValue(question.id, event.target.value)}
          options={(question.options || []).map(option => ({ value: option.value, label: option.label }))}
          style={{ display: 'flex', flexDirection: 'column', gap: 6 }}
        />
      )
    }
    if (question.type === 'multiple') {
      return (
        <Checkbox.Group
          value={(values[question.id] as string[] | undefined) || []}
          onChange={checked => setValue(question.id, checked as string[])}
          options={(question.options || []).map(option => ({ value: option.value, label: option.label }))}
          style={{ display: 'flex', flexDirection: 'column', gap: 6 }}
        />
      )
    }
    return (
      <Input.TextArea
        value={(values[question.id] as string | undefined) || ''}
        onChange={event => setValue(question.id, event.target.value)}
        placeholder={question.placeholder || '请输入'}
        rows={2}
        disabled={submitted}
      />
    )
  }

  return (
    <Card
      size="small"
      title={spec.title || '请确认'}
      style={{ marginTop: 8, borderColor: '#c7d2fe' }}
      styles={{ body: { padding: '12px 14px' } }}
    >
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        {spec.questions.map(question => (
          <div key={question.id}>
            <Text strong className="ai-clar-label">
              {question.label}
              {question.required !== false && <Text type="danger"> *</Text>}
            </Text>
            <div style={{ marginTop: 6 }}>
              {submitted && question.type !== 'text' ? (
                <Text type="secondary">
                  {question.type === 'multiple'
                    ? (values[question.id] as string[] | undefined || [])
                        .map(value => optionLabels[question.id]?.[value] || value)
                        .join('、')
                    : optionLabels[question.id]?.[String(values[question.id] || '')] || String(values[question.id] || '')}
                </Text>
              ) : renderQuestion(question)}
            </div>
          </div>
        ))}
        {error && <Text type="danger">{error}</Text>}
        <Button type="primary" size="small" onClick={submit} disabled={submitted}>
          {submitted ? '已提交' : (spec.submitLabel || '提交确认')}
        </Button>
      </Space>
    </Card>
  )
}
