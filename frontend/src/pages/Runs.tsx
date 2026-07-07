import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useBuildStore } from '../store/buildStore'
import { Clock, DollarSign, Hash, Loader2, ArrowRight } from 'lucide-react'

function StatusChip({ status }: { status: string }) {
  const map: Record<string, string> = {
    completed: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    failed: 'border-red-500/30 bg-red-500/10 text-red-300',
  }
  const cls = map[status] ?? 'border-loom-cyan/30 bg-loom-cyan/10 text-loom-cyan'
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-medium capitalize ${cls}`}>
      {status}
    </span>
  )
}

export default function Runs() {
  const { runs, fetchRuns, isLoading } = useBuildStore()

  useEffect(() => {
    fetchRuns()
  }, [fetchRuns])

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-7 w-7 animate-spin text-loom-cyan" />
      </div>
    )
  }

  if (runs.length === 0) {
    return (
      <div className="glass mx-auto max-w-md animate-fade-up p-10 text-center">
        <h2 className="mb-2 text-xl font-semibold text-white">No builds yet</h2>
        <p className="mb-6 text-slate-400">Start your first build to see it here.</p>
        <Link
          to="/"
          className="inline-flex items-center gap-2 rounded-xl bg-loom-gradient px-5 py-2.5 font-semibold text-surface-950 shadow-glow transition hover:animate-gradient-x"
        >
          New build <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
    )
  }

  return (
    <div className="animate-fade-up">
      <h1 className="mb-6 text-2xl font-bold tracking-tight text-white">Build history</h1>

      <div className="space-y-3">
        {runs.map((run, i) => (
          <Link
            key={run.run_id}
            to={`/build/${run.run_id}`}
            className="glass glass-hover group block animate-fade-up p-5"
            style={{ animationDelay: `${i * 0.04}s` }}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h3 className="truncate text-base font-semibold text-white">
                  {run.description}
                </h3>
                <div className="mt-2 flex flex-wrap items-center gap-4 text-sm text-slate-400">
                  <span className="flex items-center gap-1.5 font-mono text-xs">
                    <Hash className="h-3.5 w-3.5" />
                    {run.run_id}
                  </span>
                  <span className="flex items-center gap-1.5">
                    <Clock className="h-3.5 w-3.5" />
                    {run.duration_seconds ? `${run.duration_seconds.toFixed(1)}s` : 'in progress'}
                  </span>
                  <span className="flex items-center gap-1.5">
                    <DollarSign className="h-3.5 w-3.5" />
                    {run.total_cost_usd.toFixed(4)}
                  </span>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <StatusChip status={run.status} />
                <ArrowRight className="h-4 w-4 text-slate-600 transition group-hover:translate-x-0.5 group-hover:text-white" />
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
