import { Button, Tooltip } from 'antd'
import type { ButtonProps } from 'antd'
import { useAuthStore } from '../../store/auth'

interface PermButtonProps extends ButtonProps {
  permResource: string
  permAction: string
  noPermTooltip?: string
}

export default function PermButton({
  permResource,
  permAction,
  noPermTooltip = '无权限',
  disabled,
  children,
  ...rest
}: PermButtonProps) {
  const hasPermission = useAuthStore(s => s.hasPermission)
  const allowed = hasPermission(permResource, permAction)
  if (allowed) {
    return (
      <Button disabled={disabled} {...rest}>
        {children}
      </Button>
    )
  }
  return (
    <Tooltip title={noPermTooltip}>
      <span>
        <Button disabled {...rest}>
          {children}
        </Button>
      </span>
    </Tooltip>
  )
}
