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

const META: Record<string, { icon: typeof User; color: string }> = {
  product_manager: { icon: ClipboardList, color: '#00d9ff' },
  architect: { icon: DraftingCompass, color: '#ff5fd2' },
  frontend_dev: { icon: Code2, color: '#88c0d0' },
  backend_dev: { icon: Server, color: '#a3be8c' },
  code_reviewer: { icon: ScanSearch, color: '#d08770' },
  qa_engineer: { icon: FlaskConical, color: '#ebcb8b' },
  devops_engineer: { icon: Rocket, color: '#b48ead' },
}

export default function AgentNode({ data }: AgentNodeProps) {
  const meta = META[data.role] ?? { icon: User, color: '#9fb3c8' }
  const Icon = meta.icon
  const accent = data.isError ? '#f87171' : data.isDone ? '#34d399' : meta.color

  return (
    <div
      className="relative min-w-[150px] rounded-xl border bg-surface-850/90 px-3.5 py-3 backdrop-blur-sm transition-all duration-300"
      style={{
        borderColor: data.isActive ? accent : 'rgba(255,255,255,0.08)',
        boxShadow: data.isActive ? `0 0 22px -4px ${accent}` : '0 8px 24px -16px #000',
      }}
    >
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-white/25" />

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
          <div className="text-sm font-semibold text-white">{data.label}</div>
          <div className="text-[11px] uppercase tracking-wide text-slate-500">
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
        <div className="mt-2 flex items-center gap-2 text-[11px]" style={{ color: accent }}>
          <span
            className="h-1.5 w-1.5 rounded-full animate-glow-pulse"
            style={{ backgroundColor: accent }}
          />
          processing…
        </div>
      )}

      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-white/25" />
    </div>
  )
}
