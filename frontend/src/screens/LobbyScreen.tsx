import { useState } from 'react'
import type { GameAction } from '../game/gameReducer'
import type { GameState, Player } from '../game/types'
import type { Role } from '../net/types'
import { ScreenShell } from '../components/ScreenShell'
import { Button } from '../components/Button'
import { ArtDecoCorner } from '../components/decor/ArtDecoCorner'
import { AvatarPicker, avatarUrl } from '../components/AvatarPicker'
import { useAudio } from '../audio/AudioContext'

type LobbyScreenProps = {
  state: GameState
  dispatch: React.Dispatch<GameAction>
  role: Role
  localPlayerId: string | null
  roomCode: string
}

/**
 * Lobby unifié (refonte 2026-10-12) :
 * - Présentateur et joueurs sont tous dans state.players (is_presenter=True pour le présentateur)
 * - Cartes organiques pour chaque participant, avec avatar SVG
 * - AvatarPicker sur la gauche, 1 avatar = 1 joueur (gris si pris par un autre)
 * - Avatar tiré aléatoirement à l'entrée dans la room
 */
export function LobbyScreen({ state, dispatch, role, localPlayerId, roomCode }: LobbyScreenProps) {
  const isPresenter = role === 'presentateur'
  const joueurs = state.players.filter((p) => !p.isPresenter)
  const canStart = joueurs.length >= 2 && state.themes.length >= 1
  const { playEffect } = useAudio()

  const [editingSelf, setEditingSelf] = useState(false)
  const [nameDraft, setNameDraft] = useState('')
  const [themeLabel, setThemeLabel] = useState('')

  // Mon entrée dans players[]
  const me = state.players.find((p) => p.id === localPlayerId)
  const myAvatar = me?.avatar ?? ''
  const myDisplayName = me?.name ?? null

  // Avatars pris par d'autres (pour griser dans le picker)
  const takenBy: Record<string, string> = {}
  for (const p of state.players) {
    if (p.avatar && p.id !== localPlayerId) {
      takenBy[p.avatar] = p.name
    }
  }

  function startEditingSelf() {
    setNameDraft(myDisplayName ?? '')
    setEditingSelf(true)
  }

  function confirmRename() {
    const trimmed = nameDraft.trim()
    if (trimmed) dispatch({ type: 'RENAME_SELF', name: trimmed })
    setEditingSelf(false)
  }

  function handleSelectAvatar(avatar: string) {
    dispatch({ type: 'SET_AVATAR', avatar })
  }

  function handleAddTheme() {
    if (!themeLabel.trim()) return
    dispatch({ type: 'ADD_THEME', label: themeLabel })
    setThemeLabel('')
  }

  return (
    <ScreenShell spotlight smoke>
      <div className="flex flex-1 flex-col items-center justify-center gap-8 overflow-y-auto py-10">

        {/* Titre */}
        <div className="animate-rise-up text-center">
          <p className="mb-2 text-xs tracking-[0.5em] text-brass-400/80 uppercase">
            ★ Ce soir, sur scène ★
          </p>
          <h1 className="marquee-text font-display text-5xl font-black tracking-wide sm:text-7xl">
            Le Grand Tunneg
          </h1>
          <p className="mt-3 text-sm tracking-[0.3em] text-[#9a8d7d] uppercase">
            {isPresenter
              ? 'Préparez la partie : joueurs et thèmes'
              : 'En attente du lancement de la partie…'}
          </p>
        </div>

        {/* Corps principal : 2 colonnes sur desktop */}
        <div className="animate-rise-up flex w-full max-w-4xl flex-col gap-6 lg:flex-row lg:items-start lg:gap-8 px-4">

          {/* Colonne gauche : picker d'avatar + code room */}
          <div className="flex flex-col gap-4 lg:w-56 lg:shrink-0">

            {/* Code room */}
            <div className="rounded-2xl border border-brass-600/30 bg-gradient-to-b from-charcoal-800 to-charcoal-900 p-4 text-center shadow-stage-lg">
              <p className="text-xs tracking-[0.3em] text-[#9a8d7d] uppercase">Code room</p>
              <p className="font-display text-3xl font-black tracking-[0.3em] text-amber-glow">
                {roomCode}
              </p>
            </div>

            {/* Mon pseudo + renommage */}
            {me && (
              <div className="rounded-2xl border border-brass-600/30 bg-gradient-to-b from-charcoal-800 to-charcoal-900 p-4 shadow-stage-lg">
                <p className="mb-2 text-xs tracking-[0.2em] text-[#9a8d7d] uppercase">Vous êtes</p>
                {editingSelf ? (
                  <div className="flex flex-col gap-2">
                    <input
                      type="text"
                      value={nameDraft}
                      autoFocus
                      onChange={(e) => setNameDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') confirmRename()
                        if (e.key === 'Escape') setEditingSelf(false)
                      }}
                      maxLength={24}
                      className="w-full rounded-lg border border-brass-600/30 bg-charcoal-900/80 px-3 py-1.5 text-sm text-[#f1e6d8] outline-none focus:border-amber-glow"
                    />
                    <Button variant="primary" className="py-1.5 text-xs" onClick={confirmRename}>
                      Valider
                    </Button>
                  </div>
                ) : (
                  <div className="flex items-center justify-between">
                    <span className="font-display text-lg text-[#f1e6d8]">{myDisplayName}</span>
                    <button
                      onClick={startEditingSelf}
                      className="text-xs text-amber-glow uppercase transition-colors hover:text-amber-ember"
                    >
                      Changer
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Avatar picker */}
            {me && (
              <div className="rounded-2xl border border-brass-600/30 bg-gradient-to-b from-charcoal-800 to-charcoal-900 p-4 shadow-stage-lg">
                <p className="mb-3 text-xs tracking-[0.2em] text-[#9a8d7d] uppercase">Mon avatar</p>
                <AvatarPicker
                  selected={myAvatar}
                  onSelect={handleSelectAvatar}
                  takenBy={takenBy}
                />
              </div>
            )}
          </div>

          {/* Colonne droite : grille des participants + thèmes (présentateur) */}
          <div className="flex flex-1 flex-col gap-6">

            {/* Grille des cartes participants */}
            <div className="relative rounded-2xl border border-brass-600/30 bg-gradient-to-b from-charcoal-800 to-charcoal-900 p-5 shadow-stage-lg">
              <ArtDecoCorner position="top-left" />
              <ArtDecoCorner position="top-right" />
              <p className="mb-4 text-center text-xs tracking-[0.4em] text-brass-400/80 uppercase">
                ★ Participants ★
              </p>

              {state.players.length > 0 ? (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
                  {state.players.map((player, i) => (
                    <PlayerCard
                      key={player.id}
                      player={player}
                      isMe={player.id === localPlayerId}
                      canRemove={isPresenter && !player.isPresenter}
                      onRemove={() => dispatch({ type: 'REMOVE_PLAYER', index: i })}
                    />
                  ))}
                </div>
              ) : (
                <p className="text-center text-xs text-[#7a6f63]">
                  Aucun participant pour l'instant.
                </p>
              )}

              {joueurs.length < 2 && (
                <p className="mt-4 text-center text-xs text-[#7a6f63]">
                  Minimum 2 joueurs requis pour lancer la partie.
                </p>
              )}
            </div>

            {/* Panneau des thèmes — visible UNIQUEMENT par le Présentateur */}
            {isPresenter && (
              <div className="rounded-2xl border border-brass-600/30 bg-gradient-to-b from-charcoal-800 to-charcoal-900 p-5 shadow-stage-lg">
                <p className="mb-3 text-center text-xs tracking-[0.4em] text-brass-400/80 uppercase">
                  ★ Thèmes ★
                </p>

                <div className="flex gap-2">
                  <input
                    type="text"
                    value={themeLabel}
                    onChange={(e) => setThemeLabel(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleAddTheme() }}
                    placeholder="Nouveau thème"
                    maxLength={30}
                    className="flex-1 rounded-lg border border-brass-600/30 bg-charcoal-900/80 px-3 py-2 text-sm text-[#f1e6d8] placeholder-[#6b625b] outline-none focus:border-amber-glow"
                  />
                  <Button variant="primary" onClick={handleAddTheme} disabled={!themeLabel.trim()}>
                    Ajouter
                  </Button>
                </div>

                {state.themes.length > 0 && (
                  <ul className="mt-4 flex max-h-48 flex-col gap-1.5 overflow-y-auto pr-1">
                    {state.themes.map((theme, i) => (
                      <li
                        key={i}
                        className="flex items-center justify-between rounded-lg border border-white/5 bg-charcoal-900/60 px-4 py-2"
                      >
                        <span className="font-display text-sm text-[#f1e6d8]">{theme.label}</span>
                        <button
                          onClick={() => dispatch({ type: 'REMOVE_THEME', index: i })}
                          className="cursor-pointer text-xs text-burgundy-500 uppercase transition-colors hover:text-burgundy-500/70"
                        >
                          Retirer
                        </button>
                      </li>
                    ))}
                  </ul>
                )}

                {state.themes.length < 1 && (
                  <p className="mt-3 text-center text-xs text-[#7a6f63]">
                    Minimum 1 thème requis pour lancer la partie.
                  </p>
                )}
              </div>
            )}

            {/* Bouton lancer — présentateur uniquement */}
            {isPresenter && (
              <Button
                variant="gold"
                className="w-full py-3 text-base"
                disabled={!canStart}
                onClick={() => {
                  playEffect('theme_start')
                  dispatch({ type: 'START_GAME' })
                }}
              >
                Lancer la partie
              </Button>
            )}
          </div>
        </div>
      </div>
    </ScreenShell>
  )
}

// ─── Carte participant ─────────────────────────────────────────────────────────

type PlayerCardProps = {
  player: Player
  isMe: boolean
  canRemove: boolean
  onRemove: () => void
}

function PlayerCard({ player, isMe, canRemove, onRemove }: PlayerCardProps) {
  return (
    <div
      className={[
        'relative flex flex-col items-center gap-2 rounded-2xl border p-3 transition-all',
        isMe
          ? 'border-amber-glow/50 bg-amber-glow/5 shadow-[0_0_12px_rgba(232,163,61,0.15)]'
          : 'border-white/8 bg-charcoal-900/60',
        !player.connected && 'opacity-50',
      ].filter(Boolean).join(' ')}
    >
      {/* Badge présentateur */}
      {player.isPresenter && (
        <span className="absolute -top-2 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-brass-600 px-2 py-0.5 text-[9px] font-bold tracking-widest text-charcoal-900 uppercase">
          Présentateur
        </span>
      )}

      {/* Badge "moi" */}
      {isMe && !player.isPresenter && (
        <span className="absolute -top-2 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-amber-glow px-2 py-0.5 text-[9px] font-bold tracking-widest text-charcoal-900 uppercase">
          Vous
        </span>
      )}

      {/* Avatar */}
      <div className="h-16 w-16 overflow-hidden rounded-full border-2 border-white/10 bg-charcoal-800">
        {player.avatar ? (
          <img
            src={avatarUrl(player.avatar)}
            alt={player.avatar}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-2xl text-[#7a6f63]">?</div>
        )}
      </div>

      {/* Nom */}
      <p className="max-w-full truncate text-center font-display text-sm text-[#f1e6d8]">
        {player.name}
      </p>

      {/* Badge déconnecté */}
      {!player.connected && (
        <span className="text-[10px] text-[#7a6f63]">déconnecté</span>
      )}

      {/* Bouton retirer (présentateur uniquement, pas sur lui-même) */}
      {canRemove && (
        <button
          onClick={onRemove}
          className="mt-1 cursor-pointer text-[10px] tracking-wide text-burgundy-500 uppercase transition-colors hover:text-burgundy-500/70"
        >
          Retirer
        </button>
      )}
    </div>
  )
}
