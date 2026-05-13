import { useEffect } from 'react'

export default function usePageTitle(title: string) {
  useEffect(() => {
    const prev = document.title
    document.title = `${title} - SPC 中台`
    return () => { document.title = prev }
  }, [title])
}
