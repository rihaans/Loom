import { useEffect, useState } from 'react'
import { buildApi, Artifact } from '../api/client'

interface ArtifactPanelProps {
  runId: string
  type: string
}

export default function ArtifactPanel({ runId, type }: ArtifactPanelProps) {
  const [artifact, setArtifact] = useState<Artifact | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchArtifact = async () => {
      setLoading(true)
      setError(null)
      try {
        const response = await buildApi.getArtifact(runId, type)
        setArtifact(response.data)
      } catch (err: any) {
        if (err.response?.status === 404) {
          setError(`${type} not generated yet`)
        } else {
          setError(err.message || 'Failed to load artifact')
        }
      } finally {
        setLoading(false)
      }
    }

    fetchArtifact()
  }, [runId, type])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin h-6 w-6 border-2 border-accent border-t-transparent rounded-full" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 font-mono text-sm text-soft">
        {error}
      </div>
    )
  }

  if (!artifact) {
    return null
  }

  // Render based on artifact type
  if (type === 'prd' || type === 'architecture') {
    return (
      <div className="prose prose-invert max-w-none">
        <pre className="bg-surface-900 p-4 rounded-lg overflow-auto text-sm">
          {JSON.stringify(artifact.content, null, 2)}
        </pre>
      </div>
    )
  }

  if (type === 'code') {
    const codeFiles = artifact.content as Record<string, any>
    return (
      <div className="space-y-4">
        {Object.entries(codeFiles).map(([bundleName, bundle]: [string, any]) => (
          <div key={bundleName}>
            <h3 className="font-mono font-semibold mb-2 text-accent">{bundleName}</h3>
            {bundle.files?.map((file: any) => (
              <div key={file.path} className="mb-4">
                <div className="text-xs text-muted mb-1 font-mono">{file.path}</div>
                <pre className="bg-surface-900 p-4 rounded-lg overflow-auto text-sm font-mono">
                  {file.content}
                </pre>
              </div>
            ))}
          </div>
        ))}
      </div>
    )
  }

  if (type === 'tests') {
    const report = artifact.content
    return (
      <div className="space-y-4">
        <div className="flex gap-4 font-mono text-sm">
          <span className="text-ok">Passed: {report.passed}</span>
          <span className="text-err">Failed: {report.failed}</span>
          <span className="text-muted">Skipped: {report.skipped}</span>
          <span className="text-muted">Total: {report.total}</span>
        </div>
        {report.cases?.map((tc: any, i: number) => (
          <div
            key={i}
            className={`p-3 rounded-lg ${
              tc.passed ? 'bg-ok/10 border border-ok/30' : 'bg-err/10 border border-err/30'
            }`}
          >
            <div className="font-mono text-sm text-ink">{tc.name}</div>
            {tc.error_message && (
              <pre className="mt-2 text-xs text-err whitespace-pre-wrap">
                {tc.error_message}
              </pre>
            )}
          </div>
        ))}
      </div>
    )
  }

  // Default: JSON view
  return (
    <pre className="bg-surface-900 p-4 rounded-lg overflow-auto text-sm font-mono">
      {JSON.stringify(artifact.content, null, 2)}
    </pre>
  )
}
