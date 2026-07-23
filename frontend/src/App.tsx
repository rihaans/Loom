import { Routes, Route, Link, useLocation } from 'react-router-dom'
import Home from './pages/Home'
import Build from './pages/Build'
import Runs from './pages/Runs'

/** Animated aurora backdrop — soft cyan/magenta light through the "weave". */
function Aurora() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute inset-0 bg-surface-950" />
      <div className="absolute -top-40 left-1/4 h-[40rem] w-[40rem] rounded-full bg-loom-cyan/20 blur-[120px] animate-aurora" />
      <div
        className="absolute top-1/3 right-1/4 h-[34rem] w-[34rem] rounded-full bg-loom-magenta/20 blur-[120px] animate-aurora"
        style={{ animationDelay: '-6s' }}
      />
      <div
        className="absolute bottom-0 left-1/3 h-[30rem] w-[30rem] rounded-full bg-loom-violet/15 blur-[120px] animate-aurora"
        style={{ animationDelay: '-12s' }}
      />
      {/* faint grid */}
      <div
        className="absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage:
            'linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)',
          backgroundSize: '48px 48px',
        }}
      />
    </div>
  )
}

function Wordmark() {
  return (
    <Link to="/" className="group flex items-center gap-2.5">
      <span className="relative grid h-9 w-9 place-items-center rounded-xl bg-loom-gradient shadow-glow">
        {/* woven thread glyph */}
        <svg viewBox="0 0 24 24" className="h-5 w-5 text-surface-950" fill="none">
          <path
            d="M3 7c4 4 14 4 18 0M3 12c4 4 14 4 18 0M3 17c4 4 14 4 18 0"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        </svg>
      </span>
      <span className="text-xl font-bold tracking-tight text-gradient">Loom</span>
    </Link>
  )
}

function NavLink({ to, label }: { to: string; label: string }) {
  const { pathname } = useLocation()
  const active = pathname === to
  return (
    <Link
      to={to}
      className={`relative text-sm font-medium transition ${
        active ? 'text-white' : 'text-slate-400 hover:text-white'
      }`}
    >
      {label}
      {active && (
        <span className="absolute -bottom-[18px] left-0 h-0.5 w-full rounded-full bg-loom-gradient" />
      )}
    </Link>
  )
}

function App() {
  return (
    <div className="min-h-screen">
      <Aurora />

      <nav className="sticky top-0 z-20 border-b border-white/10 bg-surface-950/60 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <Wordmark />
          <div className="flex items-center gap-7">
            <NavLink to="/" label="New build" />
            <NavLink to="/runs" label="History" />
            <a
              href="https://github.com/rihaans/Loom"
              target="_blank"
              rel="noreferrer"
              className="hidden rounded-lg border border-white/10 px-3 py-1.5 text-sm text-slate-300 transition hover:border-white/25 hover:text-white sm:block"
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
