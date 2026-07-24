import { WebSocketMessage } from '../api/ws'
import { ArrowRight, AlertCircle, CheckCircle, Play, Zap } from 'lucide-react'

interface EventLogProps {
  messages: WebSocketMessage[]
}

export default function EventLog({ messages }: EventLogProps) {
  // Filter to only show relevant events
  const events = messages.filter(
    (m) => m.type === 'event' && m.data?.event_type !== 'llm_token'
  )

  if (events.length === 0) {
    return (
      <div className="font-mono text-sm text-muted">
        Waiting for events…
      </div>
    )
  }

  return (
    <div className="space-y-2 max-h-96 overflow-y-auto">
      {events.map((event, i) => {
        const time = new Date(event.timestamp).toLocaleTimeString()
        const eventType = event.data?.event_type

        let icon = <Zap className="w-3 h-3" />
        let color = 'text-muted'
        let label = eventType

        if (eventType === 'node_start') {
          icon = <Play className="w-3 h-3" />
          color = 'text-accent'
          label = `Started: ${event.data?.node || event.data?.agent}`
        } else if (eventType === 'node_end') {
          icon = <CheckCircle className="w-3 h-3" />
          color = 'text-ok'
          label = `Completed: ${event.data?.node || event.data?.agent}`
        } else if (eventType === 'error') {
          icon = <AlertCircle className="w-3 h-3" />
          color = 'text-err'
          label = `Error: ${event.data?.error?.slice(0, 50)}`
        } else if (eventType === 'llm_start') {
          icon = <ArrowRight className="w-3 h-3" />
          color = 'text-warn'
          label = 'LLM call started'
        } else if (eventType === 'llm_end') {
          icon = <CheckCircle className="w-3 h-3" />
          color = 'text-warn'
          label = 'LLM call completed'
        }

        return (
          <div key={i} className="flex items-start gap-2 font-mono text-sm">
            <span className="text-muted text-xs whitespace-nowrap">
              {time}
            </span>
            <span className={color}>{icon}</span>
            <span className="text-soft truncate">{label}</span>
          </div>
        )
      })}
    </div>
  )
}
