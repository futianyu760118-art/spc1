import BusinessDocumentPage from '../../Common/BusinessDocumentPage'
import { documentApi } from '../../../services/api'

export default function ProductSamples() {
  return (
    <BusinessDocumentPage
      title="产品封样"
      namespace="product_sample"
      api={{
        list: documentApi.listProductSamples,
        create: documentApi.createProductSample,
        update: documentApi.updateProductSample,
        remove: documentApi.deleteProductSample,
        versions: documentApi.listProductSampleVersions,
        publishVersion: documentApi.publishProductSampleVersion,
        publish: documentApi.publishProductSample,
        archive: documentApi.archiveProductSample,
      }}
    />
  )
}
