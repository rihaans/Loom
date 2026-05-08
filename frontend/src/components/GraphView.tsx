import { useCallback } from 'react'
import {
  ReactFlow,
  Node,
  Edge,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import AgentNode from './AgentNode'

const nodeTypes = {
  agent: AgentNode,
}

interface GraphViewProps {
  currentAgent?: string | null
}

const initialNodes: Node[] = [
  { id: 'pm', type: 'agent', position: { x: 100, y: 100 }, data: { label: 'Product Manager', role: 'product_manager' } },
  { id: 'arch', type: 'agent', position: { x: 350, y: 100 }, data: { label: 'Architect', role: 'architect' } },
  { id: 'fe', type: 'agent', position: { x: 550, y: 50 }, data: { label: 'Frontend Dev', role: 'frontend_dev' } },
  { id: 'be', type: 'agent', position: { x: 550, y: 150 }, data: { label: 'Backend Dev', role: 'backend_dev' } },
  { id: 'qa', type: 'agent', position: { x: 750, y: 100 }, data: { label: 'QA Engineer', role: 'qa_engineer' } },
  { id: 'ops', type: 'agent', position: { x: 950, y: 100 }, data: { label: 'DevOps', role: 'devops_engineer' } },
]

const initialEdges: Edge[] = [
  { id: 'pm-arch', source: 'pm', target: 'arch', animated: true },
  { id: 'arch-fe', source: 'arch', target: 'fe', animated: true },
  { id: 'arch-be', source: 'arch', target: 'be', animated: true },
  { id: 'fe-qa', source: 'fe', target: 'qa', animated: true },
  { id: 'be-qa', source: 'be', target: 'qa', animated: true },
  { id: 'qa-ops', source: 'qa', target: 'ops', animated: true },
]

export default function GraphView({ currentAgent }: GraphViewProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState(
    initialNodes.map((node) => ({
      ...node,
      data: {
        ...node.data,
        isActive: node.data.role === currentAgent,
      },
    }))
  )
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  // Update active state when currentAgent changes
  useCallback(() => {
    setNodes((nds) =>
      nds.map((node) => ({
        ...node,
        data: {
          ...node.data,
          isActive: node.data.role === currentAgent,
        },
      }))
    )
  }, [currentAgent, setNodes])

  return (
    <div className="h-[400px] bg-surface-900 rounded-lg">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#334155" gap={16} />
        <Controls />
      </ReactFlow>
    </div>
  )
}
