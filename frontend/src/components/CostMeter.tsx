import { useEffect, useState } from 'react'
import { buildApi } from '../api/client'
import { Coins, Hash } from 'lucide-react'

interface CostMeterProps {
  runId: string
}

export default function CostMeter({ runId }: CostMeterProps) {
  const [tokens, setTokens] = useState(0)
  const [cost, setCost] = useState(0)

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const { data } = await buildApi.get(runId)
        const t = (data as { total_tokens?: number }).total_tokens
        const c = (data as { total_cost?: number }).total_cost
        if (typeof t === 'number') setTokens(t)
        if (typeof c === 'number') setCost(c)
      } catch {
        /* ignore polling errors */
      }
    }
    fetchStats()
    const interval = setInterval(fetchStats, 4000)
    return () => clearInterval(interval)
  }, [runId])

  return (
    <div className="flex items-center gap-2">
      <div className="glass flex items-center gap-2 px-3 py-1.5 text-sm">
        <Hash className="h-3.5 w-3.5 text-loom-cyan" />
        <span className="font-mono tabular-nums text-white">{tokens.toLocaleString()}</span>
        <span className="text-slate-500">tokens</span>
      </div>
      <div className="glass flex items-center gap-2 px-3 py-1.5 text-sm">
        <Coins className="h-3.5 w-3.5 text-loom-magenta" />
        <span className="font-mono tabular-nums text-white">${cost.toFixed(4)}</span>
      </div>
    </div>
  )
}
