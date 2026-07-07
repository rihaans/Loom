import { useEffect } from 'react'
import {
  ReactFlow,
  Node,
  Edge,
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  useNodesState,
  useEdgesState,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import AgentNode from './AgentNode'

const nodeTypes = { agent: AgentNode }

interface GraphViewProps {
  currentAgent?: string | null
}

const initialNodes: Node[] = [
  { id: 'pm', type: 'agent', position: { x: 40, y: 170 }, data: { label: 'Product Manager', role: 'product_manager' } },
  { id: 'arch', type: 'agent', position: { x: 250, y: 170 }, data: { label: 'Architect', role: 'architect' } },
  { id: 'fe', type: 'agent', position: { x: 470, y: 20 }, data: { label: 'Frontend Dev', role: 'frontend_dev' } },
  { id: 'be', type: 'agent', position: { x: 470, y: 320 }, data: { label: 'Backend Dev', role: 'backend_dev' } },
  { id: 'review', type: 'agent', position: { x: 700, y: 170 }, data: { label: 'Code Reviewer', role: 'code_reviewer' } },
  { id: 'qa', type: 'agent', position: { x: 920, y: 170 }, data: { label: 'QA Engineer', role: 'qa_engineer' } },
  { id: 'ops', type: 'agent', position: { x: 1140, y: 170 }, data: { label: 'DevOps', role: 'devops_engineer' } },
]

const flow = (id: string, source: string, target: string, color: string): Edge => ({
  id,
  source,
  target,
  type: 'smoothstep',
  animated: true,
  style: { stroke: color, strokeWidth: 1.6, opacity: 0.7 },
  markerEnd: { type: MarkerType.ArrowClosed, color },
})

const feedback = (id: string, source: string, target: string, color: string, label: string): Edge => ({
  id,
  source,
  target,
  type: 'smoothstep',
  animated: false,
  label,
  labelStyle: { fill: color, fontSize: 10, fontWeight: 600 },
  labelBgStyle: { fill: '#0f1420', opacity: 0.85 },
  style: { stroke: color, strokeWidth: 1.4, strokeDasharray: '5 4', opacity: 0.65 },
  markerEnd: { type: MarkerType.ArrowClosed, color },
})

const initialEdges: Edge[] = [
  flow('pm-arch', 'pm', 'arch', '#00d9ff'),
  flow('arch-fe', 'arch', 'fe', '#ff5fd2'),
  flow('arch-be', 'arch', 'be', '#ff5fd2'),
  flow('fe-review', 'fe', 'review', '#88c0d0'),
  flow('be-review', 'be', 'review', '#a3be8c'),
  flow('review-qa', 'review', 'qa', '#d08770'),
  flow('qa-ops', 'qa', 'ops', '#ebcb8b'),
  // generator–critic feedback loops
  feedback('review-be', 'review', 'be', '#d08770', 'revise'),
  feedback('review-arch', 'review', 'arch', '#d08770', 'escalate'),
  feedback('qa-be', 'qa', 'be', '#ebcb8b', 'tests fail'),
]

export default function GraphView({ currentAgent }: GraphViewProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, , onEdgesChange] = useEdgesState(initialEdges)

  // Highlight the node matching the live current agent.
  useEffect(() => {
    setNodes((nds) =>
      nds.map((node) => ({
        ...node,
        data: { ...node.data, isActive: node.data.role === currentAgent },
      }))
    )
  }, [currentAgent, setNodes])

  return (
    <div className="h-[420px] overflow-hidden rounded-xl border border-white/10 bg-surface-950/60">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.12 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
      >
        <Background variant={BackgroundVariant.Dots} color="#22304a" gap={20} size={1} />
        <Controls showInteractive={false} className="!border-white/10" />
      </ReactFlow>
    </div>
  )
}
