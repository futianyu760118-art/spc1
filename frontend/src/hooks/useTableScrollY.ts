import { useEffect, useState } from 'react'
import type { RefObject } from 'react'

/** 实测容器高度，扣除表头/分页实测高度，得出表格体 scroll.y，保证窗口不出现滚动条（配合页面根节点 height: calc(100vh - 104px) + overflow: hidden 使用） */
export function useTableScrollY(wrapRef: RefObject<HTMLDivElement | null>, deps: unknown[] = []) {
  const [scrollY, setScrollY] = useState<number>(400)
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const update = () => {
      const thead = el.querySelector('.ant-table-thead') as HTMLElement | null
      const pag = el.querySelector('.ant-pagination') as HTMLElement | null
      const theadH = thead ? thead.offsetHeight : 39
      // 分页: 自身高度 + 上外距16; 卡片: 底部内边距4 + 边框2; 无分页时仅卡片部分
      const extra = pag ? pag.offsetHeight + 16 + 4 + 2 : 4 + 2
      const y = el.clientHeight - theadH - extra
      setScrollY(Math.max(y, 120))
    }
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    if (el.firstElementChild) ro.observe(el.firstElementChild as HTMLElement)
    return () => ro.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wrapRef, ...deps])
  return scrollY
}
