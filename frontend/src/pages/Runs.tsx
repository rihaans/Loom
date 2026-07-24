import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useBuildStore } from '../store/buildStore'
import { Clock, DollarSign, Hash, Loader2, ArrowRight } from 'lucide-react'

function StatusChip({ status }: { status: string }) {
  const map: Record<string, string> = {
    completed: 'border-ok/30 bg-ok/10 text-ok',
    failed: 'border-err/30 bg-err/10 text-err',
  }
  const cls = map[status] ?? 'border-accent/30 bg-accent/10 text-accent'
  return (
    <span className={`rounded-full border px-3 py-1 font-mono text-xs capitalize ${cls}`}>
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
        <Loader2 className="h-7 w-7 animate-spin text-accent" />
      </div>
    )
  }

  if (runs.length === 0) {
    return (
      <div className="glass mx-auto max-w-md animate-fade-up p-10 text-center">
        <h2 className="mb-2 text-xl font-semibold text-ink">No builds yet</h2>
        <p className="mb-6 text-soft">Start your first build to see it here.</p>
        <Link
          to="/"
          className="inline-flex items-center gap-2 rounded-lg bg-gold-foil px-5 py-2.5 font-mono font-semibold text-surface-950 shadow-glow transition hover:brightness-105"
        >
          new build <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
    )
  }

  return (
    <div className="animate-fade-up">
      <h1 className="mb-6 font-mono text-2xl font-bold tracking-tight text-ink">Build history</h1>

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
                <h3 className="truncate text-base font-semibold text-ink">
                  {run.description}
                </h3>
                <div className="mt-2 flex flex-wrap items-center gap-4 font-mono text-sm text-soft">
                  <span className="flex items-center gap-1.5 text-xs">
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
                <ArrowRight className="h-4 w-4 text-faint transition group-hover:translate-x-0.5 group-hover:text-ink" />
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
