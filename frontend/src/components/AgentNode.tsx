import { Handle, Position } from '@xyflow/react'
import { User, Cpu, Code, TestTube, Server, Users } from 'lucide-react'

interface AgentNodeProps {
  data: {
    label: string
    role: string
    isActive?: boolean
    isDone?: boolean
    isError?: boolean
  }
}

const ICONS: Record<string, typeof User> = {
  product_manager: Users,
  architect: Cpu,
  frontend_dev: Code,
  backend_dev: Server,
  qa_engineer: TestTube,
  devops_engineer: Server,
}

export default function AgentNode({ data }: AgentNodeProps) {
  const Icon = ICONS[data.role] || User

  return (
    <div
      className={`
        px-4 py-3 rounded-lg border-2 bg-surface-800 min-w-[140px]
        ${data.isActive ? 'border-primary-500 agent-active' : 'border-surface-600'}
        ${data.isDone ? 'border-green-500' : ''}
        ${data.isError ? 'border-red-500' : ''}
      `}
    >
      <Handle type="target" position={Position.Left} className="!bg-surface-600" />

      <div className="flex items-center gap-2">
        <div
          className={`
            p-2 rounded-lg
            ${data.isActive ? 'bg-primary-500/20 text-primary-400' : 'bg-surface-700 text-gray-400'}
            ${data.isDone ? 'bg-green-500/20 text-green-400' : ''}
            ${data.isError ? 'bg-red-500/20 text-red-400' : ''}
          `}
        >
          <Icon className="w-4 h-4" />
        </div>
        <span className="font-medium text-sm">{data.label}</span>
      </div>

      {data.isActive && (
        <div className="mt-2 flex items-center gap-2 text-xs text-primary-400">
          <div className="w-2 h-2 bg-primary-400 rounded-full animate-pulse" />
          Working...
        </div>
      )}

      <Handle type="source" position={Position.Right} className="!bg-surface-600" />
    </div>
  )
}
