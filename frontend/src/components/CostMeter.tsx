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
        const response = await buildApi.get(runId)
        // Stats would come from the run status or a separate endpoint
        // For now, we'll update from the artifact if available
      } catch (err) {
        // Ignore errors
      }
    }

    const interval = setInterval(fetchStats, 5000)
    fetchStats()

    return () => clearInterval(interval)
  }, [runId])

  return (
    <div className="flex items-center gap-6 text-sm">
      <div className="flex items-center gap-2 text-gray-400">
        <Hash className="w-4 h-4" />
        <span>{tokens.toLocaleString()} tokens</span>
      </div>
      <div className="flex items-center gap-2 text-gray-400">
        <Coins className="w-4 h-4" />
        <span>${cost.toFixed(4)}</span>
      </div>
    </div>
  )
}
