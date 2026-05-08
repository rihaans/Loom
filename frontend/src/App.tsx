import { Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import Build from './pages/Build'
import Runs from './pages/Runs'

function App() {
  return (
    <div className="min-h-screen bg-surface-900">
      <nav className="bg-surface-800 border-b border-surface-700 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <a href="/" className="flex items-center gap-2">
            <span className="text-2xl">🔨</span>
            <span className="text-xl font-bold text-white">AgentForge</span>
          </a>
          <div className="flex items-center gap-6">
            <a href="/" className="text-gray-300 hover:text-white transition">
              New Build
            </a>
            <a href="/runs" className="text-gray-300 hover:text-white transition">
              History
            </a>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-8">
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
