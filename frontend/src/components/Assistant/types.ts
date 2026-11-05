import { AgentSkillBrief } from '../../services/agent'

export interface TeamAgent {
  id: number
  name: string
  capabilities?: Array<{ code: string; name: string }>
  skills?: AgentSkillBrief[]
}
