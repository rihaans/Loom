import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useBuildStore } from '../store/buildStore'
import { Rocket, Sparkles } from 'lucide-react'

const EXAMPLES = [
  "Build a todo app with FastAPI backend and React frontend",
  "Create a REST API for a blog with user authentication",
  "Build a real-time chat application with WebSockets",
  "Create a simple e-commerce product listing page",
]

export default function Home() {
  const navigate = useNavigate()
  const { startBuild, isLoading, error } = useBuildStore()
  const [description, setDescription] = useState('')
  const [model, setModel] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!description.trim()) return

    try {
      const runId = await startBuild(description, model || undefined)
      navigate(`/build/${runId}`)
    } catch (err) {
      // Error handled by store
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold mb-4">
          Build Software with AI Agents
        </h1>
        <p className="text-gray-400 text-lg">
          Describe your project and let our autonomous team of AI agents build it for you.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Project Description
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe what you want to build..."
            className="w-full h-32 px-4 py-3 bg-surface-800 border border-surface-700 rounded-lg
                       text-white placeholder-gray-500 focus:outline-none focus:ring-2
                       focus:ring-primary-500 focus:border-transparent resize-none"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Model (optional)
          </label>
          <input
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="e.g., anthropic:claude-sonnet-4-20250514"
            className="w-full px-4 py-3 bg-surface-800 border border-surface-700 rounded-lg
                       text-white placeholder-gray-500 focus:outline-none focus:ring-2
                       focus:ring-primary-500 focus:border-transparent"
          />
        </div>

        {error && (
          <div className="p-4 bg-red-900/20 border border-red-800 rounded-lg text-red-400">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={isLoading || !description.trim()}
          className="w-full py-4 bg-primary-600 hover:bg-primary-700 disabled:bg-gray-700
                     disabled:cursor-not-allowed rounded-lg font-semibold text-white
                     transition flex items-center justify-center gap-2"
        >
          {isLoading ? (
            <>
              <div className="animate-spin h-5 w-5 border-2 border-white border-t-transparent rounded-full" />
              Starting...
            </>
          ) : (
            <>
              <Rocket className="w-5 h-5" />
              Start Building
            </>
          )}
        </button>
      </form>

      <div className="mt-12">
        <div className="flex items-center gap-2 text-gray-400 mb-4">
          <Sparkles className="w-4 h-4" />
          <span className="text-sm">Try an example</span>
        </div>
        <div className="grid gap-3">
          {EXAMPLES.map((example, i) => (
            <button
              key={i}
              onClick={() => setDescription(example)}
              className="text-left p-4 bg-surface-800 hover:bg-surface-700 border border-surface-700
                         rounded-lg text-gray-300 transition"
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
