import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useBuildStore } from '../store/buildStore'
import { useWebSocket } from '../api/ws'
import GraphView from '../components/GraphView'
import ArtifactPanel from '../components/ArtifactPanel'
import EventLog from '../components/EventLog'
import CostMeter from '../components/CostMeter'
import { Loader2, Wifi } from 'lucide-react'

const TABS = ['graph', 'prd', 'architecture', 'code', 'tests', 'devops'] as const

function StatusChip({ status }: { status: string }) {
  const map: Record<string, string> = {
    completed: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    failed: 'border-red-500/30 bg-red-500/10 text-red-300',
  }
  const cls = map[status] ?? 'border-loom-cyan/30 bg-loom-cyan/10 text-loom-cyan'
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${cls}`}>
      {status}
    </span>
  )
}

export default function Build() {
  const { runId } = useParams<{ runId: string }>()
  const { currentRun, fetchRun, updateRunProgress } = useBuildStore()
  const { messages, isConnected, lastToken } = useWebSocket(runId || null)
  const [activeTab, setActiveTab] = useState<string>('graph')

  useEffect(() => {
    if (runId) fetchRun(runId)
  }, [runId, fetchRun])

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
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-7 w-7 animate-spin text-loom-cyan" />
      </div>
    )
  }

  const isComplete = currentRun.status === 'completed' || currentRun.status === 'failed'
  const progress = Math.max(0, Math.min(100, currentRun.progress || 0))

  return (
    <div className="animate-fade-up space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            {currentRun.description.length > 64
              ? currentRun.description.slice(0, 64) + '…'
              : currentRun.description}
          </h1>
          <div className="mt-2 flex items-center gap-3 text-sm text-slate-400">
            <span className="font-mono text-xs">{currentRun.run_id}</span>
            <StatusChip status={currentRun.status} />
            {isConnected && (
              <span className="flex items-center gap-1.5 text-emerald-400">
                <Wifi className="h-3.5 w-3.5" />
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400/60" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
                </span>
                live
              </span>
            )}
          </div>
        </div>
        <CostMeter runId={runId!} />
      </div>

      {/* Progress */}
      <div className="space-y-1.5">
        <div className="flex justify-between text-xs text-slate-500">
          <span>{currentRun.current_agent?.replace(/_/g, ' ') || 'starting…'}</span>
          <span className="font-mono">{progress}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-white/5">
          <div
            className={`relative h-full rounded-full bg-loom-gradient bg-[length:200%_200%] transition-all duration-700 ease-out ${
              isComplete ? '' : 'animate-gradient-x shimmer-sheen'
            }`}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Main grid */}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {/* Tabs */}
          <div className="flex flex-wrap gap-1 rounded-xl border border-white/10 bg-white/[0.02] p-1">
            {TABS.map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`rounded-lg px-3.5 py-1.5 text-sm font-medium capitalize transition ${
                  activeTab === tab
                    ? 'bg-loom-gradient text-surface-950 shadow-glow'
                    : 'text-slate-400 hover:bg-white/5 hover:text-white'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="glass min-h-[460px] p-2">
            {activeTab === 'graph' ? (
              <GraphView currentAgent={currentRun.current_agent} />
            ) : (
              <div className="p-4">
                <ArtifactPanel runId={runId!} type={activeTab} />
              </div>
            )}
          </div>
        </div>

        {/* Side column */}
        <div className="space-y-4">
          {!isComplete && lastToken && (
            <div className="glass p-4">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Live output
              </h3>
              <pre className="max-h-48 overflow-y-auto whitespace-pre-wrap font-mono text-xs text-slate-300">
                {lastToken.slice(-600)}
              </pre>
            </div>
          )}

          <div className="glass p-4">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Event stream
            </h3>
            <EventLog messages={messages} />
          </div>
        </div>
      </div>
    </div>
  )
}
