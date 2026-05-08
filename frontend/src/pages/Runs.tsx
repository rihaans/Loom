import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useBuildStore } from '../store/buildStore'
import { Clock, DollarSign, Hash } from 'lucide-react'

export default function Runs() {
  const { runs, fetchRuns, isLoading } = useBuildStore()

  useEffect(() => {
    fetchRuns()
  }, [fetchRuns])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin h-8 w-8 border-2 border-primary-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  if (runs.length === 0) {
    return (
      <div className="text-center py-12">
        <h2 className="text-xl font-semibold mb-2">No builds yet</h2>
        <p className="text-gray-400 mb-6">Start your first build to see it here.</p>
        <Link
          to="/"
          className="px-6 py-3 bg-primary-600 hover:bg-primary-700 rounded-lg font-semibold transition"
        >
          New Build
        </Link>
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Build History</h1>

      <div className="space-y-4">
        {runs.map((run) => (
          <Link
            key={run.run_id}
            to={`/build/${run.run_id}`}
            className="block p-6 bg-surface-800 hover:bg-surface-700 border border-surface-700
                       rounded-lg transition"
          >
            <div className="flex items-start justify-between">
              <div>
                <h3 className="font-semibold text-lg">{run.description.slice(0, 60)}...</h3>
                <div className="flex items-center gap-4 mt-2 text-sm text-gray-400">
                  <span className="flex items-center gap-1">
                    <Hash className="w-4 h-4" />
                    {run.run_id}
                  </span>
                  <span className="flex items-center gap-1">
                    <Clock className="w-4 h-4" />
                    {run.duration_seconds ? `${run.duration_seconds.toFixed(1)}s` : 'In progress'}
                  </span>
                  <span className="flex items-center gap-1">
                    <DollarSign className="w-4 h-4" />
                    ${run.total_cost_usd.toFixed(4)}
                  </span>
                </div>
              </div>
              <span
                className={`px-3 py-1 rounded-full text-sm font-medium ${
                  run.status === 'completed'
                    ? 'bg-green-900/30 text-green-400'
                    : run.status === 'failed'
                    ? 'bg-red-900/30 text-red-400'
                    : 'bg-blue-900/30 text-blue-400'
                }`}
              >
                {run.status}
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
