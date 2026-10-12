import type { GameAction } from '../game/gameReducer'
import { ScreenShell } from '../components/ScreenShell'
import { Button } from '../components/Button'
import { ScoreBoard } from '../components/ScoreBoard'
import { MiniProgressBar } from '../components/MiniProgressBar'
import { squareFullClasses } from '../components/SquareColors'
import type { SquareColor } from '../game/types'
import { createTheme } from '../game/rules'

type StyleguideScreenProps = {
  dispatch: React.Dispatch<GameAction>
}

type SwatchGroup = {
  name: string
  usage: string
  swatches: { label: string; className: string }[]
}

const SWATCH_GROUPS: SwatchGroup[] = [
  {
    name: 'Charcoal',
    usage: 'Fonds de scène, panneaux, dégradés sombres',
    swatches: [
      { label: '950', className: 'bg-charcoal-950' },
      { label: '900', className: 'bg-charcoal-900' },
      { label: '800', className: 'bg-charcoal-800' },
      { label: '700', className: 'bg-charcoal-700' },
    ],
  },
  {
    name: 'Amber',
    usage: 'CTA primaires, score du joueur actif, case "en jeu" (jaune)',
    swatches: [
      { label: 'glow', className: 'bg-amber-glow' },
      { label: 'dim', className: 'bg-amber-dim' },
      { label: 'ember', className: 'bg-amber-ember' },
    ],
  },
  {
    name: 'Burgundy',
    usage: 'Danger / erreur / suppression, rideaux de scène, chrono < 10s',
    swatches: [
      { label: '900', className: 'bg-burgundy-900' },
      { label: '700', className: 'bg-burgundy-700' },
      { label: '500', className: 'bg-burgundy-500' },
    ],
  },
  {
    name: 'Brass',
    usage: 'Bordures dorées, ornements Art Déco, accents "secondary"/"gold"',
    swatches: [
      { label: '400', className: 'bg-brass-400' },
      { label: '600', className: 'bg-brass-600' },
    ],
  },
  {
    name: 'Nightblue',
    usage: 'Touches froides en arrière-plan uniquement (aurore radiale) — pas de composant UI direct',
    swatches: [
      { label: '900', className: 'bg-nightblue-900' },
      { label: '700', className: 'bg-nightblue-700' },
      { label: '500', className: 'bg-nightblue-500' },
    ],
  },
  {
    name: 'Sunset',
    usage: 'Dégradés de titres (marquee-text), bouton "gold", case validée (jaune)',
    swatches: [
      { label: 'gold', className: 'bg-sunset-gold' },
      { label: 'orange', className: 'bg-sunset-orange' },
      { label: 'pink', className: 'bg-sunset-pink' },
      { label: 'violet', className: 'bg-sunset-violet' },
    ],
  },
]

const SQUARE_COLORS: SquareColor[] = ['empty', 'yellow', 'green', 'gray', 'black']
const SQUARE_LABELS: Record<SquareColor, string> = {
  empty: 'À venir',
  yellow: 'En jeu',
  green: 'Franchie',
  gray: 'Validée (coffrée)',
  black: 'Annulée (passée)',
}

const demoPlayers = [
  { id: 'demo-1', name: 'Alice', points: 12, connected: true, avatar: 'alice' },
  { id: 'demo-2', name: 'Bruno', points: 7, connected: true, avatar: 'bob' },
]

const demoTheme = (() => {
  const t = createTheme('Cinéma des années 80')
  t.discovered = true
  t.progressValue = 4
  t.validatedSquares = 2
  t.nullified = [3]
  return t
})()

function SectionTitle({ children, subtitle }: { children: React.ReactNode; subtitle?: string }) {
  return (
    <div className="mb-4 flex flex-col gap-1">
      <h2 className="font-display text-2xl font-bold text-[#f1e6d8]">{children}</h2>
      {subtitle && <p className="text-xs tracking-wide text-[#9a8d7d]">{subtitle}</p>}
    </div>
  )
}

/**
 * Page de démonstration interne du design system (Bloc 6). Rend la palette
 * complète de tokens `--color-*`, l'échelle typographique et les composants
 * de base réutilisables, dans un seul écran de référence visuelle.
 *
 * Accès : non exposée dans le flux de jeu normal — atteignable via le
 * paramètre d'URL `?debug=styleguide` (voir App.tsx), pour vérification en
 * développement uniquement.
 */
export function StyleguideScreen({ dispatch }: StyleguideScreenProps) {
  return (
    <ScreenShell>
      <div className="flex flex-1 flex-col gap-12 py-8">
        <div className="text-center">
          <p className="mb-2 text-xs tracking-[0.4em] text-brass-400/80 uppercase">Bloc 6 — Design system</p>
          <h1 className="marquee-text font-display text-4xl font-black sm:text-5xl">
            Styleguide
          </h1>
          <p className="mt-2 text-sm text-[#9a8d7d]">
            Jazz Club feutré / La La Land — palette, typographie, composants
          </p>
        </div>

        {/* Palette de couleurs */}
        <section>
          <SectionTitle subtitle="Tokens --color-* définis dans src/index.css, voir le commentaire d'en-tête pour la convention d'usage complète">
            Palette
          </SectionTitle>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {SWATCH_GROUPS.map((group) => (
              <div
                key={group.name}
                className="rounded-xl border border-brass-600/25 bg-charcoal-900/60 p-4"
              >
                <h3 className="font-display mb-1 text-lg font-semibold text-[#f1e6d8]">
                  {group.name}
                </h3>
                <p className="mb-3 text-xs text-[#9a8d7d]">{group.usage}</p>
                <div className="flex gap-2">
                  {group.swatches.map((s) => (
                    <div key={s.label} className="flex flex-col items-center gap-1">
                      <div
                        className={`h-12 w-12 rounded-md border border-white/10 ${s.className}`}
                      />
                      <span className="text-[10px] text-[#7a6f63]">{s.label}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Typographie */}
        <section>
          <SectionTitle subtitle='--font-display: "Playfair Display" (titres) · --font-body: "Manrope" (texte courant)'>
            Typographie
          </SectionTitle>
          <div className="flex flex-col gap-4 rounded-xl border border-brass-600/25 bg-charcoal-900/60 p-6">
            <h1 className="font-display text-5xl font-black text-[#f1e6d8]">Titre display H1</h1>
            <h2 className="font-display text-3xl font-bold text-[#f1e6d8]">Titre display H2</h2>
            <h2 className="marquee-text font-display text-3xl font-bold">Titre dégradé (marquee-text)</h2>
            <p className="font-body text-base text-[#f1e6d8]">
              Texte courant en Manrope — utilisé pour les paragraphes, labels et contenus de jeu.
            </p>
            <p className="text-xs tracking-[0.3em] text-[#9a8d7d] uppercase">
              Label discret tracking large uppercase
            </p>
          </div>
        </section>

        {/* Boutons */}
        <section>
          <SectionTitle subtitle="Composant Button.tsx, 5 variants">
            Boutons
          </SectionTitle>
          <div className="flex flex-wrap gap-4 rounded-xl border border-brass-600/25 bg-charcoal-900/60 p-6">
            <Button variant="primary">Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="danger">Danger</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="gold">Gold</Button>
            <Button variant="primary" disabled>
              Disabled
            </Button>
          </div>
        </section>

        {/* ScoreBoard */}
        <section>
          <SectionTitle subtitle="Composant ScoreBoard.tsx">Tableau de scores</SectionTitle>
          <div className="rounded-xl border border-brass-600/25 bg-charcoal-900/60 p-6">
            <ScoreBoard players={demoPlayers} currentPlayerIndex={0} />
          </div>
        </section>

        {/* Cases / couleurs de progression */}
        <section>
          <SectionTitle subtitle="Composant SquareColors.ts — les 5 états d'une case de tunnel">
            Cases du tunnel
          </SectionTitle>
          <div className="flex flex-wrap gap-6 rounded-xl border border-brass-600/25 bg-charcoal-900/60 p-6">
            {SQUARE_COLORS.map((c) => (
              <div key={c} className="flex flex-col items-center gap-2">
                <div
                  className={`flex h-16 w-12 items-end justify-center rounded-md border-2 pb-1.5 text-sm font-bold ${squareFullClasses[c]}`}
                >
                  #
                </div>
                <span className="text-xs text-[#9a8d7d]">{SQUARE_LABELS[c]}</span>
              </div>
            ))}
          </div>
        </section>

        {/* MiniProgressBar */}
        <section>
          <SectionTitle subtitle="Composant MiniProgressBar.tsx — utilisé dans les cartes de sélection de thème">
            Mini barre de progression
          </SectionTitle>
          <div className="max-w-sm rounded-xl border border-brass-600/25 bg-charcoal-900/60 p-6">
            <MiniProgressBar theme={demoTheme} />
          </div>
        </section>

        <div className="flex justify-center pt-4">
          <Button variant="ghost" onClick={() => dispatch({ type: 'QUIT_TO_MENU' })}>
            Retour au menu
          </Button>
        </div>
      </div>
    </ScreenShell>
  )
}
