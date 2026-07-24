import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useBuildStore } from '../store/buildStore'
import { ArrowRight, Loader2 } from 'lucide-react'

const EXAMPLES = [
  'Build a todo app with FastAPI backend and React frontend',
  'Create a REST API for a blog with user authentication',
  'Build a real-time chat application with WebSockets',
  'Create a CLI tool that converts markdown files to PDF',
]

const TEAM = ['PM', 'Architect', 'Frontend', 'Backend', 'Reviewer', 'QA', 'DevOps']

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
        <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-line bg-white/[0.02] px-3.5 py-1.5 font-mono text-xs text-soft">
          <span className="h-1.5 w-1.5 rounded-full bg-accent shadow-glow" />
          seven AI agents · generate → review → test → ship
        </div>
        <h1 className="text-balance text-5xl font-bold leading-[1.1] tracking-tight text-ink sm:text-6xl">
          Type an idea.
          <br />
          <span className="text-gradient">Watch a team build it.</span>
        </h1>
        <p className="mx-auto mt-5 max-w-xl text-lg text-soft">
          Loom turns a sentence into a working, tested, containerized project —
          PM, architect, parallel devs, a code reviewer, QA, and DevOps, all collaborating live.
        </p>
      </div>

      {/* Prompt card */}
      <form
        onSubmit={handleSubmit}
        className="glass border-accent-hairline mt-10 animate-fade-up space-y-4 p-5 sm:p-6"
        style={{ animationDelay: '0.08s' }}
      >
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Describe what you want to build…"
          rows={4}
          className="w-full resize-none rounded-lg border border-line bg-surface-950/60 px-4 py-3 text-ink placeholder-muted outline-none transition focus:border-accent/50 focus:ring-1 focus:ring-accent/25"
        />

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <input
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="model (optional) · e.g. anthropic:claude-sonnet-4-5"
            className="flex-1 rounded-lg border border-line bg-surface-950/60 px-4 py-2.5 font-mono text-sm text-ink placeholder-muted outline-none transition focus:border-accent/50"
          />
          <button
            type="submit"
            disabled={isLoading || !description.trim()}
            className="group inline-flex items-center justify-center gap-2 rounded-lg bg-gold-foil px-6 py-2.5 font-mono font-semibold text-surface-950 shadow-glow transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> starting…
              </>
            ) : (
              <>
                start building
                <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
              </>
            )}
          </button>
        </div>

        {error && (
          <div className="rounded-lg border border-err/30 bg-err/10 px-4 py-3 text-sm text-err">
            {error}
          </div>
        )}
      </form>

      {/* Team strip — monochrome, name-only (as in the terminal) */}
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        {TEAM.map((label, i) => (
          <span
            key={label}
            className="animate-fade-up rounded-full border border-line bg-white/[0.02] px-3 py-1 font-mono text-xs text-soft"
            style={{ animationDelay: `${0.15 + i * 0.04}s` }}
          >
            <span className="mr-1.5 align-middle text-accent">◇</span>
            {label}
          </span>
        ))}
      </div>

      {/* Examples */}
      <div className="mt-12">
        <div className="mb-3 flex items-center gap-2 font-mono text-sm text-soft">
          <span className="text-accent">◇</span>
          try an example
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {EXAMPLES.map((example, i) => (
            <button
              key={i}
              onClick={() => setDescription(example)}
              className="glass glass-hover animate-fade-up p-4 text-left text-sm text-soft hover:text-ink"
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
