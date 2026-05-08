import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useBuildStore } from '../store/buildStore'
import { useWebSocket } from '../api/ws'
import GraphView from '../components/GraphView'
import ArtifactPanel from '../components/ArtifactPanel'
import EventLog from '../components/EventLog'
import CostMeter from '../components/CostMeter'

export default function Build() {
  const { runId } = useParams<{ runId: string }>()
  const { currentRun, fetchRun, updateRunProgress } = useBuildStore()
  const { messages, isConnected, lastToken } = useWebSocket(runId || null)
  const [activeTab, setActiveTab] = useState<string>('graph')

  useEffect(() => {
    if (runId) {
      fetchRun(runId)
    }
  }, [runId, fetchRun])

  // Update progress from WebSocket
  useEffect(() => {
    const statusMessages = messages.filter((m) => m.type === 'status' || m.type === 'event')
    const lastStatus = statusMessages[statusMessages.length - 1]
    if (lastStatus?.data) {
      updateRunProgress(
        lastStatus.data.progress || currentRun?.progress || 0,
        lastStatus.data.current_agent || lastStatus.data.node
      )
    }
  }, [messages, updateRunProgress, currentRun?.progress])

  if (!currentRun) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin h-8 w-8 border-2 border-primary-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  const isComplete = currentRun.status === 'completed' || currentRun.status === 'failed'

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{currentRun.description.slice(0, 50)}...</h1>
          <div className="flex items-center gap-4 mt-2 text-sm text-gray-400">
            <span>Run: {currentRun.run_id}</span>
            <span
              className={`px-2 py-0.5 rounded ${
                currentRun.status === 'completed'
                  ? 'bg-green-900/30 text-green-400'
                  : currentRun.status === 'failed'
                  ? 'bg-red-900/30 text-red-400'
                  : 'bg-blue-900/30 text-blue-400'
              }`}
            >
              {currentRun.status}
            </span>
            {isConnected && (
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                Live
              </span>
            )}
          </div>
        </div>
        <CostMeter runId={runId!} />
      </div>

      {/* Progress bar */}
      <div className="h-2 bg-surface-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-primary-500 transition-all duration-500"
          style={{ width: `${currentRun.progress}%` }}
        />
      </div>

      {/* Main content */}
      <div className="grid grid-cols-3 gap-6">
        {/* Graph and artifacts */}
        <div className="col-span-2 space-y-6">
          {/* Tabs */}
          <div className="flex gap-2 border-b border-surface-700">
            {['graph', 'prd', 'architecture', 'code', 'tests', 'devops'].map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 font-medium transition border-b-2 -mb-px ${
                  activeTab === tab
                    ? 'border-primary-500 text-white'
                    : 'border-transparent text-gray-400 hover:text-gray-200'
                }`}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="bg-surface-800 rounded-lg p-6 min-h-[400px]">
            {activeTab === 'graph' ? (
              <GraphView currentAgent={currentRun.current_agent} />
            ) : (
              <ArtifactPanel runId={runId!} type={activeTab} />
            )}
          </div>
        </div>

        {/* Event log and output */}
        <div className="space-y-6">
          {/* Live output */}
          {!isComplete && lastToken && (
            <div className="bg-surface-800 rounded-lg p-4">
              <h3 className="text-sm font-medium text-gray-400 mb-2">Live Output</h3>
              <pre className="font-mono text-sm text-gray-300 whitespace-pre-wrap max-h-48 overflow-y-auto">
                {lastToken.slice(-500)}
              </pre>
            </div>
          )}

          {/* Event log */}
          <div className="bg-surface-800 rounded-lg p-4">
            <h3 className="text-sm font-medium text-gray-400 mb-2">Events</h3>
            <EventLog messages={messages} />
          </div>
        </div>
      </div>
    </div>
  )
}
