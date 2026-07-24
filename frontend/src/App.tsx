import { Routes, Route, Link, useLocation } from 'react-router-dom'
import Home from './pages/Home'
import Build from './pages/Build'
import Runs from './pages/Runs'

/** Calm charcoal ground with one quiet nod to the name — faint woven threads. */
function Weave() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute inset-0 bg-surface-950" />
      {/* soft champagne wash at the top */}
      <div className="absolute inset-0 bg-gold-radial" />
      {/* woven thread hairlines */}
      <svg className="absolute inset-x-0 top-0 h-[52rem] w-full opacity-[0.06]" preserveAspectRatio="none">
        <defs>
          <pattern id="weave" width="1200" height="132" patternUnits="userSpaceOnUse">
            {[18, 62, 106].map((y) => (
              <path
                key={y}
                d={`M-40 ${y}c150 34 300 34 450 0s300-34 450 0 300 34 450 0 300-34 450 0`}
                fill="none"
                stroke="#c9b68c"
                strokeWidth="1"
              />
            ))}
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#weave)" />
      </svg>
    </div>
  )
}

function Wordmark() {
  return (
    <Link to="/" className="group flex items-center gap-2.5">
      <span className="relative grid h-9 w-9 place-items-center rounded-lg border border-accent/25 bg-accent/10">
        {/* woven thread glyph */}
        <svg viewBox="0 0 24 24" className="h-5 w-5 text-accent" fill="none">
          <path
            d="M3 7c4 4 14 4 18 0M3 12c4 4 14 4 18 0M3 17c4 4 14 4 18 0"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        </svg>
      </span>
      <span className="font-mono text-lg font-semibold tracking-tight text-accent">loom</span>
    </Link>
  )
}

function NavLink({ to, label }: { to: string; label: string }) {
  const { pathname } = useLocation()
  const active = pathname === to
  return (
    <Link
      to={to}
      className={`relative font-mono text-sm transition ${
        active ? 'text-ink' : 'text-soft hover:text-ink'
      }`}
    >
      {label}
      {active && (
        <span className="absolute -bottom-[18px] left-0 h-px w-full bg-accent" />
      )}
    </Link>
  )
}

function App() {
  return (
    <div className="min-h-screen">
      <Weave />

      <nav className="sticky top-0 z-20 border-b border-line bg-surface-950/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <Wordmark />
          <div className="flex items-center gap-7">
            <NavLink to="/" label="new build" />
            <NavLink to="/runs" label="history" />
            <a
              href="https://github.com/rihaans/Loom"
              target="_blank"
              rel="noreferrer"
              className="hidden rounded-lg border border-line px-3 py-1.5 font-mono text-sm text-soft transition hover:border-accent/30 hover:text-ink sm:block"
            >
              GitHub
            </a>
          </div>
        </div>
      </nav>

      <main className="mx-auto max-w-7xl px-6 py-10">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/build/:runId" element={<Build />} />
          <Route path="/runs" element={<Runs />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
