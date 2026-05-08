import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

export interface BuildRequest {
  description: string
  interactive?: boolean
  model?: string
}

export interface BuildResponse {
  run_id: string
  thread_id: string
  status: string
  message: string
}

export interface RunStatus {
  run_id: string
  thread_id: string
  status: string
  description: string
  started_at: string
  completed_at?: string
  current_agent?: string
  progress: number
  error?: string
}

export interface RunSummary {
  run_id: string
  description: string
  status: string
  started_at: string
  duration_seconds?: number
  total_tokens: number
  total_cost_usd: number
}

export interface Artifact {
  type: string
  content: any
  format: string
}

export const buildApi = {
  start: (request: BuildRequest) =>
    api.post<BuildResponse>('/build', request),

  list: () =>
    api.get<RunSummary[]>('/runs'),

  get: (runId: string) =>
    api.get<RunStatus>(`/runs/${runId}`),

  getArtifact: (runId: string, type: string) =>
    api.get<Artifact>(`/runs/${runId}/artifacts/${type}`),
}

export default api
