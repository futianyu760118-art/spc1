import { qualityApi } from '../../../../services/quality'
import { registerRemote } from './registry'

registerRemote('supplier', {
  search: async (keyword: string) => {
    const res: any = await qualityApi.searchSuppliers(keyword)
    return res.data?.items || []
  },
  toOption: (item: any) => ({
    value: item.supplier_name,
    label: `${item.supplier_name}（${item.supplier_code}）`,
    supplier_code: item.supplier_code,
  }),
})
