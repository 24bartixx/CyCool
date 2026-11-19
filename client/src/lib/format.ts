const eur0 = new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })
const num0 = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 })
const num1 = new Intl.NumberFormat('en-GB', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const num2 = new Intl.NumberFormat('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export const DASH = '—'

export const eur = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? DASH : eur0.format(v))
export const int = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? DASH : num0.format(v))
export const dec1 = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? DASH : num1.format(v))
export const dec2 = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? DASH : num2.format(v))
export const km = (v: number | null | undefined) => (v == null ? DASH : `${num2.format(v)} km`)
export const metres = (v: number | null | undefined) => (v == null ? DASH : `${num0.format(v)} m`)
export const celsius = (v: number | null | undefined) => (v == null ? DASH : `${num1.format(v)} °C`)

/** Compact euros for presets and chips: €25k, €1.2M. */
export const eurShort = (v: number) =>
  v >= 1_000_000 ? `€${num1.format(v / 1_000_000)}M` : v >= 1000 ? `€${num0.format(v / 1000)}k` : eur0.format(v)
