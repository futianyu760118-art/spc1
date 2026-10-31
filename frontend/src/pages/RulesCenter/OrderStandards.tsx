import BusinessDocumentPage from '../Common/BusinessDocumentPage'
import { documentApi } from '../../services/api'
import { useAuthStore } from '../../store/auth'

const api = {
  list: documentApi.listOrderStandards,
  create: documentApi.createOrderStandard,
  update: documentApi.updateOrderStandard,
  remove: documentApi.deleteOrderStandard,
  versions: documentApi.listOrderStandardVersions,
  publishVersion: documentApi.publishOrderStandardVersion,
  publish: documentApi.publishOrderStandard,
  archive: documentApi.archiveOrderStandard,
}

const fieldConfigApi = {
  list: documentApi.listOrderStandardFieldConfigs,
  create: documentApi.createOrderStandardFieldConfig,
  update: documentApi.updateOrderStandardFieldConfig,
  remove: documentApi.deleteOrderStandardFieldConfig,
}

export default function OrderStandards() {
  const hasPermission = useAuthStore(s => s.hasPermission)

  return (
    <BusinessDocumentPage
      title="订单标准"
      namespace="order_standard"
      api={api}
      fieldConfigApi={fieldConfigApi}
      canConfig={hasPermission('rules.order_standards', 'update')}
    />
  )
}
