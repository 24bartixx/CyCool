const eur0 = new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })
const eur2c = new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2 })
const num0 = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 })
const num1 = new Intl.NumberFormat('en-GB', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const num2 = new Intl.NumberFormat('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export const DASH = '—'

export const eur = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? DASH : eur0.format(v))
export const eur2 = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? DASH : eur2c.format(v))
export const int = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? DASH : num0.format(v))
export const dec1 = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? DASH : num1.format(v))
export const dec2 = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? DASH : num2.format(v))
export const km = (v: number | null | undefined) => (v == null ? DASH : `${num2.format(v)} km`)
export const metres = (v: number | null | undefined) => (v == null ? DASH : `${num0.format(v)} m`)
export const celsius = (v: number | null | undefined) => (v == null ? DASH : `${num1.format(v)} °C`)

const upTo1 = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 1 })

/**
 * Compact euros for the UI: €850, €5.2k, €12k, €1.2M (no trailing ".0", no long runs of zeros).
 * One decimal below 10k / 10M, where it still matters; whole thousands / millions above.
 */
export const eurShort = (v: number | null | undefined) => {
  if (v == null || !Number.isFinite(v)) return DASH
  const sign = v < 0 ? '−' : ''
  const a = Math.abs(v)
  if (a >= 1_000_000) return `${sign}€${(a >= 10_000_000 ? num0 : upTo1).format(a / 1_000_000)}M`
  if (a >= 999.5) {
    const k = a / 1000
    // 999,960 would round to "1,000k": show it as €1M instead.
    if (k >= 999.5) return `${sign}€1M`
    return `${sign}€${(k >= 9.95 ? num0 : upTo1).format(k)}k`
  }
  return `${sign}${eur0.format(a)}`
}
