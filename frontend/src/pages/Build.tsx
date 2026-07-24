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
    completed: 'border-ok/30 bg-ok/10 text-ok',
    failed: 'border-err/30 bg-err/10 text-err',
  }
  const cls = map[status] ?? 'border-accent/30 bg-accent/10 text-accent'
  return (
    <span className={`rounded-full border px-2.5 py-0.5 font-mono text-xs capitalize ${cls}`}>
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
        <Loader2 className="h-7 w-7 animate-spin text-accent" />
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
          <h1 className="text-2xl font-bold tracking-tight text-ink">
            {currentRun.description.length > 64
              ? currentRun.description.slice(0, 64) + '…'
              : currentRun.description}
          </h1>
          <div className="mt-2 flex items-center gap-3 font-mono text-sm text-soft">
            <span className="text-xs">{currentRun.run_id}</span>
            <StatusChip status={currentRun.status} />
            {isConnected && (
              <span className="flex items-center gap-1.5 text-ok">
                <Wifi className="h-3.5 w-3.5" />
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-ok/60" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-ok" />
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
        <div className="flex justify-between font-mono text-xs text-muted">
          <span>{currentRun.current_agent?.replace(/_/g, ' ') || 'starting…'}</span>
          <span>{progress}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-white/[0.04]">
          <div
            className={`relative h-full rounded-full bg-gold-foil transition-all duration-700 ease-out ${
              isComplete ? '' : 'shimmer-sheen'
            }`}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Main grid */}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {/* Tabs */}
          <div className="flex flex-wrap gap-1 rounded-xl border border-line bg-white/[0.02] p-1">
            {TABS.map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`rounded-lg px-3.5 py-1.5 font-mono text-sm capitalize transition ${
                  activeTab === tab
                    ? 'bg-gold-foil font-semibold text-surface-950 shadow-glow'
                    : 'text-soft hover:bg-white/5 hover:text-ink'
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
              <h3 className="mb-2 font-mono text-xs font-semibold uppercase tracking-wide text-muted">
                Live output
              </h3>
              <pre className="max-h-48 overflow-y-auto whitespace-pre-wrap font-mono text-xs text-soft">
                {lastToken.slice(-600)}
              </pre>
            </div>
          )}

          <div className="glass p-4">
            <h3 className="mb-2 font-mono text-xs font-semibold uppercase tracking-wide text-muted">
              Event stream
            </h3>
            <EventLog messages={messages} />
          </div>
        </div>
      </div>
    </div>
  )
}
