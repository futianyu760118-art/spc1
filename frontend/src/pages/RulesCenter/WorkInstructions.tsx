import BusinessDocumentPage from '../Common/BusinessDocumentPage'
import { documentApi } from '../../services/api'

export default function WorkInstructions() {
  return (
    <BusinessDocumentPage
      title="作业指导书"
      namespace="work_instruction"
      api={{
        list: documentApi.listWorkInstructions,
        create: documentApi.createWorkInstruction,
        update: documentApi.updateWorkInstruction,
        remove: documentApi.deleteWorkInstruction,
        versions: documentApi.listWorkInstructionVersions,
        publishVersion: documentApi.publishWorkInstructionVersion,
        publish: documentApi.publishWorkInstruction,
        archive: documentApi.archiveWorkInstruction,
      }}
    />
  )
}
