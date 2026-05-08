import { create } from 'zustand'
import { buildApi, RunStatus, RunSummary } from '../api/client'

interface BuildState {
  // Current build
  currentRunId: string | null
  currentRun: RunStatus | null

  // Build list
  runs: RunSummary[]

  // UI state
  isLoading: boolean
  error: string | null

  // Actions
  startBuild: (description: string, model?: string) => Promise<string>
  fetchRun: (runId: string) => Promise<void>
  fetchRuns: () => Promise<void>
  setCurrentRun: (run: RunStatus | null) => void
  updateRunProgress: (progress: number, currentAgent?: string) => void
  setError: (error: string | null) => void
  clearError: () => void
}

export const useBuildStore = create<BuildState>((set, get) => ({
  currentRunId: null,
  currentRun: null,
  runs: [],
  isLoading: false,
  error: null,

  startBuild: async (description: string, model?: string) => {
    set({ isLoading: true, error: null })
    try {
      const response = await buildApi.start({ description, model })
      const runId = response.data.run_id
      set({ currentRunId: runId })
      return runId
    } catch (error: any) {
      set({ error: error.message || 'Failed to start build' })
      throw error
    } finally {
      set({ isLoading: false })
    }
  },

  fetchRun: async (runId: string) => {
    try {
      const response = await buildApi.get(runId)
      set({ currentRun: response.data, currentRunId: runId })
    } catch (error: any) {
      set({ error: error.message || 'Failed to fetch run' })
    }
  },

  fetchRuns: async () => {
    set({ isLoading: true })
    try {
      const response = await buildApi.list()
      set({ runs: response.data })
    } catch (error: any) {
      set({ error: error.message || 'Failed to fetch runs' })
    } finally {
      set({ isLoading: false })
    }
  },

  setCurrentRun: (run) => set({ currentRun: run }),

  updateRunProgress: (progress, currentAgent) => {
    const { currentRun } = get()
    if (currentRun) {
      set({
        currentRun: {
          ...currentRun,
          progress,
          current_agent: currentAgent,
        },
      })
    }
  },

  setError: (error) => set({ error }),
  clearError: () => set({ error: null }),
}))
