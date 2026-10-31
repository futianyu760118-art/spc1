import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { Input } from 'antd'
import type { InputRef } from 'antd'
import type { FilterValue, SorterResult, TableCurrentDataSource, TablePaginationConfig } from 'antd/es/table/interface'

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
  filterToQuery?: (filters: Record<string, FilterValue | null>) => TFilters
  debounceMs?: number
  initialKeyword?: string
  initialFilters?: Record<string, FilterValue | null>
  extraDeps?: ReadonlyArray<unknown>
}

export interface UseAntTableQueryResult {
  data: any[]
  loading: boolean
  total: number
  keyword: string
  filters: Record<string, FilterValue | null>
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
      pagination: TablePaginationConfig,
      filters: Record<string, FilterValue | null>,
      sorter: SorterResult<any> | SorterResult<any>[],
      extra: TableCurrentDataSource<any>,
    ) => void
  }
  reload: () => void
}

export function useAntTableQuery<TFilters extends Record<string, unknown> = Record<string, unknown>>(
  options: UseAntTableQueryOptions<TFilters>,
): UseAntTableQueryResult {
  const { fetchData, defaultPageSize = 20, filterToQuery, debounceMs = 300, initialKeyword = '', initialFilters, extraDeps = [] } = options

  const [keyword, setKeyword] = useState<string>(initialKeyword)
  const [debouncedKeyword, setDebouncedKeyword] = useState<string>(initialKeyword)
  const [page, setPage] = useState<number>(1)
  const [pageSize, setPageSize] = useState<number>(defaultPageSize)
  const [sortBy, setSortBy] = useState<string | undefined>(undefined)
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc' | undefined>(undefined)
  const [filters, setFilters] = useState<Record<string, FilterValue | null>>(initialFilters ?? {})
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
  }, [debouncedKeyword, sortBy, sortOrder, JSON.stringify(filters), ...extraDeps])

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
  }, [page, pageSize, debouncedKeyword, sortBy, sortOrder, JSON.stringify(filters), reloadTick, ...extraDeps])

  const onChange = useCallback(
    (
      pagination: TablePaginationConfig,
      nextFilters: Record<string, FilterValue | null>,
      sorter: SorterResult<any> | SorterResult<any>[],
    ) => {
      if (pagination.current) setPage(pagination.current)
      if (pagination.pageSize && pagination.pageSize !== pageSize) {
        setPageSize(pagination.pageSize)
        setPage(1)
      }
      setFilters(nextFilters || {})
      const single = Array.isArray(sorter) ? sorter[0] : sorter
      const rawField = single?.field
      const fieldKey = typeof rawField === 'string'
        ? rawField
        : typeof single?.columnKey === 'string'
          ? single.columnKey
          : undefined
      const order = single?.order
      if (fieldKey && (order === 'ascend' || order === 'descend')) {
        setSortBy(fieldKey)
        setSortOrder(order === 'ascend' ? 'asc' : 'desc')
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
      onChange: (p: number, ps: number) => onChange(
        { current: p, pageSize: ps } as TablePaginationConfig,
        filters,
        { order: sortOrder === 'asc' ? 'ascend' : sortOrder === 'desc' ? 'descend' : null, field: sortBy } as SorterResult<any>,
      ),
    },
    onChange,
  }

  return { data, loading, total, keyword, filters, searchInput, tableProps, reload }
}
