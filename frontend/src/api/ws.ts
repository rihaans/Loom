import { useEffect, useRef, useState, useCallback } from 'react'

export interface WebSocketMessage {
  type: string
  data: any
  timestamp: string
}

export function useWebSocket(runId: string | null) {
  const [messages, setMessages] = useState<WebSocketMessage[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [lastToken, setLastToken] = useState<string>('')
  const wsRef = useRef<WebSocket | null>(null)

  const connect = useCallback(() => {
    if (!runId) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/${runId}`)

    ws.onopen = () => {
      setIsConnected(true)
      console.log('WebSocket connected')
    }

    ws.onmessage = (event) => {
      const message: WebSocketMessage = JSON.parse(event.data)
      setMessages((prev) => [...prev, message])

      // Track tokens
      if (message.type === 'event' && message.data?.token) {
        setLastToken((prev) => prev + message.data.token)
      }
    }

    ws.onclose = () => {
      setIsConnected(false)
      console.log('WebSocket disconnected')
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }

    wsRef.current = ws
  }, [runId])

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }, [])

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [connect, disconnect])

  const clearTokens = useCallback(() => {
    setLastToken('')
  }, [])

  return {
    messages,
    isConnected,
    lastToken,
    clearTokens,
  }
}
