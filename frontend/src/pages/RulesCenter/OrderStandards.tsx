import BusinessDocumentPage from '../Common/BusinessDocumentPage'
import { documentApi } from '../../services/api'

export default function OrderStandards() {
  return (
    <BusinessDocumentPage
      title="订单标准"
      namespace="order_standard"
      api={{
        list: documentApi.listOrderStandards,
        create: documentApi.createOrderStandard,
        update: documentApi.updateOrderStandard,
        remove: documentApi.deleteOrderStandard,
        versions: documentApi.listOrderStandardVersions,
        publish: documentApi.publishOrderStandardVersion,
      }}
    />
  )
}
