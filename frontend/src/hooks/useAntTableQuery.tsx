import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { Input } from 'antd'
import type { InputRef } from 'antd'

export interface AntTableFetchParams {
  page: number
  page_size: number
  keyword?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
  [k: string]: unknown
}

export interface AntTableFetchResult<T = unknown> {
  items: T[]
  total: number
}

export interface UseAntTableQueryOptions<TFilters extends Record<string, unknown> = Record<string, unknown>> {
  fetchData: (params: AntTableFetchParams & TFilters) => Promise<AntTableFetchResult>
  defaultPageSize?: number
  filterToQuery?: (filters: Record<string, (string | number)[] | null>) => TFilters
  debounceMs?: number
  initialKeyword?: string
}

export interface UseAntTableQueryResult {
  data: any[]
  loading: boolean
  total: number
  keyword: string
  searchInput: React.ReactNode
  tableProps: {
    dataSource: any[]
    loading: boolean
    pagination: {
      current: number
      pageSize: number
      total: number
      showSizeChanger: boolean
      showTotal: (total: number) => string
      pageSizeOptions: string[]
      onChange: (page: number, pageSize: number) => void
    }
    onChange: (
      pagination: { current?: number; pageSize?: number },
      filters: Record<string, (string | number)[] | null>,
      sorter: { field?: string | number; order?: 'ascend' | 'descend' | null },
    ) => void
  }
  reload: () => void
}

export function useAntTableQuery<TFilters extends Record<string, unknown> = Record<string, unknown>>(
  options: UseAntTableQueryOptions<TFilters>,
): UseAntTableQueryResult {
  const { fetchData, defaultPageSize = 20, filterToQuery, debounceMs = 300, initialKeyword = '' } = options

  const [keyword, setKeyword] = useState<string>(initialKeyword)
  const [debouncedKeyword, setDebouncedKeyword] = useState<string>(initialKeyword)
  const [page, setPage] = useState<number>(1)
  const [pageSize, setPageSize] = useState<number>(defaultPageSize)
  const [sortBy, setSortBy] = useState<string | undefined>(undefined)
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc' | undefined>(undefined)
  const [filters, setFilters] = useState<Record<string, (string | number)[] | null>>({})
  const [data, setData] = useState<any[]>([])
  const [total, setTotal] = useState<number>(0)
  const [loading, setLoading] = useState<boolean>(false)
  const [reloadTick, setReloadTick] = useState<number>(0)

  const abortRef = useRef<AbortController | null>(null)
  const inputRef = useRef<InputRef>(null)

  useEffect(() => {
    const t = setTimeout(() => setDebouncedKeyword(keyword), debounceMs)
    return () => clearTimeout(t)
  }, [keyword, debounceMs])

  useEffect(() => {
    setPage(1)
  }, [debouncedKeyword, sortBy, sortOrder, JSON.stringify(filters)])

  useEffect(() => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setLoading(true)
    const extra = filterToQuery ? filterToQuery(filters) : ({} as TFilters)
    const params: AntTableFetchParams & TFilters = {
      page,
      page_size: pageSize,
      keyword: debouncedKeyword || undefined,
      sort_by: sortBy,
      sort_order: sortOrder,
      ...extra,
    }
    fetchData(params)
      .then((res) => {
        if (ctrl.signal.aborted) return
        setData(res.items || [])
        setTotal(res.total || 0)
      })
      .catch((err) => {
        if (ctrl.signal.aborted) return
        console.error('[useAntTableQuery] fetch failed:', err)
        setData([])
        setTotal(0)
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false)
      })
    return () => ctrl.abort()
  }, [page, pageSize, debouncedKeyword, sortBy, sortOrder, JSON.stringify(filters), reloadTick])

  const onChange = useCallback(
    (
      pagination: { current?: number; pageSize?: number },
      nextFilters: Record<string, (string | number)[] | null>,
      sorter: { field?: string | number; order?: 'ascend' | 'descend' | null },
    ) => {
      if (pagination.current) setPage(pagination.current)
      if (pagination.pageSize && pagination.pageSize !== pageSize) {
        setPageSize(pagination.pageSize)
        setPage(1)
      }
      setFilters(nextFilters || {})
      const fieldKey = typeof sorter.field === 'string' ? sorter.field : undefined
      if (fieldKey && (sorter.order === 'ascend' || sorter.order === 'descend')) {
        setSortBy(fieldKey)
        setSortOrder(sorter.order === 'ascend' ? 'asc' : 'desc')
      } else {
        setSortBy(undefined)
        setSortOrder(undefined)
      }
    },
    [pageSize],
  )

  const reload = useCallback(() => setReloadTick((n) => n + 1), [])

  const searchInput = useMemo(
    () => (
      <Input.Search
        ref={inputRef}
        placeholder="搜索"
        allowClear
        value={keyword}
        onChange={(e) => setKeyword(e.target.value)}
        style={{ width: 240 }}
      />
    ),
    [keyword],
  )

  const tableProps: UseAntTableQueryResult['tableProps'] = {
    dataSource: data,
    loading,
    pagination: {
      current: page,
      pageSize,
      total,
      showSizeChanger: true,
      showTotal: (t: number) => `共 ${t} 条`,
      pageSizeOptions: ['20', '50', '100'],
      onChange: (p: number, ps: number) => onChange({ current: p, pageSize: ps }, filters, { order: sortOrder === 'asc' ? 'ascend' : sortOrder === 'desc' ? 'descend' : null, field: sortBy }),
    },
    onChange,
  }

  return { data, loading, total, keyword, searchInput, tableProps, reload }
}
