import { useApi, type Health } from '../api/client.ts'

export default function ApiStatus() {
  const { data, loading } = useApi<Health>('/health')

  let dotClass = 'bg-warning'
  let label = 'Checking API…'
  if (!loading) {
    if (data?.status === 'ok') {
      dotClass = 'bg-success'
      label = `API ok · PostGIS ${data.postgis}`
    } else {
      dotClass = 'bg-danger'
      label = 'API unavailable'
    }
  }

  return (
    <span className="flex items-center gap-2 text-xs text-muted">
      <span className={`size-2 rounded-full ${dotClass}`} />
      {label}
    </span>
  )
}
