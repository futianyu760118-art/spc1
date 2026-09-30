import { Checkbox, Radio } from 'antd'
import { registerWidget } from '../registry'
import type { WidgetProps } from '../types'

function RadioCardsWidget({ field, value, onChange }: WidgetProps) {
  return (
    <div className="clm-rcards">
      {(field.options || []).map(opt => {
        const [zh, ...rest] = opt.label.split(' ')
        const en = rest.join(' ')
        const on = value === opt.value
        return (
          <Radio key={opt.value} className={`clm-rcard${on ? ' on' : ''}`} value={opt.value}
            checked={on} onChange={() => onChange?.(opt.value)}>
            <span className="rc-txt">
              <span className="tt">{on ? '■' : '□'} {zh}</span>
              {en ? <span className="en">{en}</span> : null}
            </span>
          </Radio>
        )
      })}
    </div>
  )
}

function CheckboxCardsWidget({ field, value, onChange }: WidgetProps) {
  const selected: string[] = Array.isArray(value) ? value : []
  const toggle = (v: string, checked: boolean) =>
    onChange?.(checked ? [...selected, v] : selected.filter(x => x !== v))
  return (
    <div className="clm-ccards">
      {(field.options || []).map(opt => (
        <label key={opt.value} className={`clm-ccard${selected.includes(opt.value) ? ' on' : ''}`}>
          <Checkbox checked={selected.includes(opt.value)} onChange={e => toggle(opt.value, e.target.checked)} />
          <span>{opt.label.split(' ')[0]}</span>
        </label>
      ))}
    </div>
  )
}

registerWidget('radio_cards', RadioCardsWidget)
registerWidget('checkbox_cards', CheckboxCardsWidget)
