import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useBuildStore } from '../store/buildStore'
import { ArrowRight, Sparkles, Loader2 } from 'lucide-react'

const EXAMPLES = [
  'Build a todo app with FastAPI backend and React frontend',
  'Create a REST API for a blog with user authentication',
  'Build a real-time chat application with WebSockets',
  'Create a CLI tool that converts markdown files to PDF',
]

const TEAM = [
  { label: 'PM', color: '#00d9ff' },
  { label: 'Architect', color: '#ff5fd2' },
  { label: 'Frontend', color: '#88c0d0' },
  { label: 'Backend', color: '#a3be8c' },
  { label: 'Reviewer', color: '#d08770' },
  { label: 'QA', color: '#ebcb8b' },
  { label: 'DevOps', color: '#b48ead' },
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
    } catch {
      /* surfaced via store.error */
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      {/* Hero */}
      <div className="animate-fade-up text-center">
        <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3.5 py-1.5 text-xs text-slate-300">
          <span className="h-1.5 w-1.5 rounded-full bg-loom-cyan shadow-glow" />
          Seven AI agents · generate → review → test → ship
        </div>
        <h1 className="text-balance text-5xl font-bold leading-[1.1] tracking-tight sm:text-6xl">
          Type an idea.
          <br />
          <span className="text-gradient">Watch a team build it.</span>
        </h1>
        <p className="mx-auto mt-5 max-w-xl text-lg text-slate-400">
          Loom turns a sentence into a working, tested, containerized project —
          PM, architect, parallel devs, a code reviewer, QA, and DevOps, all collaborating live.
        </p>
      </div>

      {/* Prompt card */}
      <form
        onSubmit={handleSubmit}
        className="glass border-gradient mt-10 animate-fade-up space-y-4 p-5 sm:p-6"
        style={{ animationDelay: '0.08s' }}
      >
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Describe what you want to build…"
          rows={4}
          className="w-full resize-none rounded-xl border border-white/10 bg-surface-950/60 px-4 py-3 text-white placeholder-slate-500 outline-none transition focus:border-loom-cyan/50 focus:ring-2 focus:ring-loom-cyan/20"
        />

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <input
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="model (optional) · e.g. anthropic:claude-sonnet-4-5"
            className="flex-1 rounded-xl border border-white/10 bg-surface-950/60 px-4 py-2.5 font-mono text-sm text-white placeholder-slate-600 outline-none transition focus:border-loom-cyan/50"
          />
          <button
            type="submit"
            disabled={isLoading || !description.trim()}
            className="group inline-flex items-center justify-center gap-2 rounded-xl bg-loom-gradient bg-[length:200%_200%] px-6 py-2.5 font-semibold text-surface-950 shadow-glow transition hover:animate-gradient-x disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Starting…
              </>
            ) : (
              <>
                Start building
                <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
              </>
            )}
          </button>
        </div>

        {error && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}
      </form>

      {/* Team strip */}
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        {TEAM.map((a, i) => (
          <span
            key={a.label}
            className="animate-fade-up rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs text-slate-300"
            style={{ animationDelay: `${0.15 + i * 0.04}s` }}
          >
            <span
              className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full align-middle"
              style={{ backgroundColor: a.color }}
            />
            {a.label}
          </span>
        ))}
      </div>

      {/* Examples */}
      <div className="mt-12">
        <div className="mb-3 flex items-center gap-2 text-sm text-slate-400">
          <Sparkles className="h-4 w-4 text-loom-cyan" />
          Try an example
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {EXAMPLES.map((example, i) => (
            <button
              key={i}
              onClick={() => setDescription(example)}
              className="glass glass-hover animate-fade-up p-4 text-left text-sm text-slate-300"
              style={{ animationDelay: `${0.2 + i * 0.05}s` }}
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
