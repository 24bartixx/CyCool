import { useEffect, useState } from 'react'

// Requests go to /api/* and Vite proxies them to the backend (see vite.config.ts),
// so there is no CORS setup or backend URL to configure in the browser.
const API_BASE = '/api'

export type Place = {
  id: number
  name: string
  city: string
  category: string
  latitude: number
  longitude: number
}

export type Health = {
  status: 'ok' | 'degraded' | 'error'
  database: boolean
  postgis: string | null
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal })
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

type ApiState<T> = { data?: T; error?: Error; loading: boolean }

/** Minimal GET hook. Swap for TanStack Query if you need caching/mutations. */
export function useApi<T>(path: string): ApiState<T> {
  const [state, setState] = useState<ApiState<T>>({ loading: true })

  useEffect(() => {
    const controller = new AbortController()
    apiGet<T>(path, controller.signal)
      .then((data) => setState({ data, loading: false }))
      .catch((error: Error) => {
        if (!controller.signal.aborted) setState({ error, loading: false })
      })
    return () => controller.abort()
  }, [path])

  return state
}
