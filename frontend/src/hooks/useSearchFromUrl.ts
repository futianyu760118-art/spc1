import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';

/**
 * 从 URL 参数中读取搜索关键字并自动填充
 * @param onSearch 搜索回调函数
 * @returns 搜索关键字
 */
export function useSearchFromUrl(onSearch: (keyword: string) => void): string | null {
  const [searchParams, setSearchParams] = useSearchParams();
  const searchKeyword = searchParams.get('search');

  useEffect(() => {
    if (searchKeyword) {
      // 自动触发搜索
      onSearch(searchKeyword);
      
      // 清除 URL 参数，避免刷新页面时重复搜索
      const newParams = new URLSearchParams(searchParams);
      newParams.delete('search');
      setSearchParams(newParams, { replace: true });
    }
  }, [searchKeyword, onSearch, searchParams, setSearchParams]);

  return searchKeyword;
}
