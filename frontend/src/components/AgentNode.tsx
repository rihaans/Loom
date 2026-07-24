import { Handle, Position } from '@xyflow/react'
import {
  ClipboardList,
  DraftingCompass,
  Code2,
  Server,
  ScanSearch,
  FlaskConical,
  Rocket,
  User,
  Check,
} from 'lucide-react'

interface AgentNodeProps {
  data: {
    label: string
    role: string
    isActive?: boolean
    isDone?: boolean
    isError?: boolean
  }
}

// Monochrome, name-only identity (as in the terminal renderer): every agent
// shares the single champagne accent; state is carried by sage/rose, not hue.
const ICONS: Record<string, typeof User> = {
  product_manager: ClipboardList,
  architect: DraftingCompass,
  frontend_dev: Code2,
  backend_dev: Server,
  code_reviewer: ScanSearch,
  qa_engineer: FlaskConical,
  devops_engineer: Rocket,
}

const CHAMPAGNE = '#c9b68c'
const SAGE = '#8fb08a'
const ROSE = '#c58a8a'
const IDLE = '#6a707a'

export default function AgentNode({ data }: AgentNodeProps) {
  const Icon = ICONS[data.role] ?? User
  const active = data.isError ? ROSE : data.isDone ? SAGE : data.isActive ? CHAMPAGNE : IDLE
  const accent = active

  return (
    <div
      className="relative min-w-[150px] rounded-xl border bg-surface-850/90 px-3.5 py-3 transition-all duration-300"
      style={{
        borderColor: data.isActive || data.isDone || data.isError ? accent : '#2a2e36',
        boxShadow: data.isActive ? `0 0 22px -6px ${accent}` : '0 8px 24px -18px #000',
      }}
    >
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-faint" />

      <div className="flex items-center gap-2.5">
        <div
          className="grid h-8 w-8 place-items-center rounded-lg transition"
          style={{
            backgroundColor: `${accent}22`,
            color: accent,
            boxShadow: data.isActive ? `0 0 0 1px ${accent}55 inset` : 'none',
          }}
        >
          {data.isDone ? <Check className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
        </div>
        <div className="leading-tight">
          <div className="font-mono text-sm font-semibold text-ink">{data.label}</div>
          <div className="font-mono text-[11px] uppercase tracking-wide text-muted">
            {data.isError
              ? 'error'
              : data.isDone
                ? 'done'
                : data.isActive
                  ? 'working'
                  : 'idle'}
          </div>
        </div>
      </div>

      {data.isActive && (
        <div className="mt-2 flex items-center gap-2 font-mono text-[11px]" style={{ color: accent }}>
          <span
            className="h-1.5 w-1.5 rounded-full animate-glow-pulse"
            style={{ backgroundColor: accent }}
          />
          processing…
        </div>
      )}

      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-faint" />
    </div>
  )
}
