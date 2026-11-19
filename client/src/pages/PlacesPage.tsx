import { useApi, type Place } from '../api/client.ts'

export default function PlacesPage() {
  const { data: places, error, loading } = useApi<Place[]>('/places')

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight">Places</h1>
      <p className="mt-1 text-muted">
        Mock data served by{' '}
        <code className="rounded bg-border/60 px-1.5 py-0.5 text-sm">GET /api/places</code>
      </p>

      {loading && <p className="mt-8 text-muted">Loading…</p>}

      {error && (
        <div className="mt-8 rounded-lg border border-danger/30 bg-danger/10 p-4 text-danger">
          Couldn't load places: {error.message}
        </div>
      )}

      {places && (
        <ul className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {places.map((place) => (
            <li key={place.id} className="rounded-xl border border-border bg-surface p-5 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <h2 className="font-medium">{place.name}</h2>
                <span className="shrink-0 rounded-full bg-secondary/20 px-2 py-0.5 text-xs font-medium text-secondary-foreground">
                  {place.category}
                </span>
              </div>
              <p className="mt-1 text-sm text-muted">{place.city}</p>
              <a
                href={`https://www.openstreetmap.org/?mlat=${place.latitude}&mlon=${place.longitude}#map=17/${place.latitude}/${place.longitude}`}
                target="_blank"
                rel="noreferrer"
                className="mt-4 inline-block font-mono text-xs text-primary hover:underline"
              >
                {place.latitude.toFixed(4)}, {place.longitude.toFixed(4)}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
