/**
 * Champ de bokeh : lumières floutées en arrière-plan façon ville nocturne
 * hors-focus (référence La La Land). Purement décoratif, pointer-events
 * désactivés, animations en transform/opacity uniquement pour rester léger.
 */
const DOTS: Array<{
  top: string
  left: string
  size: number
  color: string
  duration: string
  delay: string
  anim: 'bokeh-float' | 'bokeh-float-alt'
}> = [
  { top: '8%', left: '12%', size: 90, color: 'rgba(255,154,86,0.45)', duration: '9s', delay: '0s', anim: 'bokeh-float' },
  { top: '15%', left: '80%', size: 130, color: 'rgba(255,111,145,0.35)', duration: '11s', delay: '1.2s', anim: 'bokeh-float-alt' },
  { top: '62%', left: '6%', size: 110, color: 'rgba(39,65,127,0.4)', duration: '13s', delay: '0.4s', anim: 'bokeh-float' },
  { top: '78%', left: '88%', size: 80, color: 'rgba(232,163,61,0.4)', duration: '10s', delay: '2s', anim: 'bokeh-float-alt' },
  { top: '38%', left: '48%', size: 150, color: 'rgba(124,79,140,0.25)', duration: '15s', delay: '0.8s', anim: 'bokeh-float' },
  { top: '28%', left: '28%', size: 60, color: 'rgba(255,215,122,0.35)', duration: '8s', delay: '1.6s', anim: 'bokeh-float-alt' },
  { top: '86%', left: '42%', size: 100, color: 'rgba(255,154,86,0.3)', duration: '12s', delay: '0.6s', anim: 'bokeh-float' },
]

export function BokehField() {
  return (
    <div className="bokeh-field" aria-hidden="true">
      {DOTS.map((d, i) => (
        <div
          key={i}
          className="bokeh-dot"
          style={{
            top: d.top,
            left: d.left,
            width: d.size,
            height: d.size,
            background: `radial-gradient(circle, ${d.color}, transparent 70%)`,
            animation: `${d.anim} ${d.duration} ease-in-out ${d.delay} infinite`,
          }}
        />
      ))}
    </div>
  )
}
