import { useState } from 'react'
import type { GameAction } from '../game/gameReducer'
import type { GameState } from '../game/types'
import type { Role } from '../net/types'
import { ScreenShell } from '../components/ScreenShell'
import { Button } from '../components/Button'
import { ArtDecoCorner } from '../components/decor/ArtDecoCorner'
import { AvatarPicker } from '../components/AvatarPicker'
import { useAudio } from '../audio/AudioContext'

type LobbyScreenProps = {
  state: GameState
  dispatch: React.Dispatch<GameAction>
  role: Role
  localPlayerId: string | null
  roomCode: string
}

/**
 * Lobby unique (fusion 2026-10-11 des anciens écrans MenuScreen + ThemesScreen).
 * Ajout 2026-10-12 : chaque participant (joueur et Présentateur) peut choisir
 * son icône de personnage parmi 16 emojis dans le lobby.
 */
export function LobbyScreen({ state, dispatch, role, localPlayerId, roomCode }: LobbyScreenProps) {
  const isPresenter = role === 'presentateur'
  const canStart = state.players.length >= 2 && state.themes.length >= 1
  const { playEffect } = useAudio()

  const [editingSelf, setEditingSelf] = useState(false)
  const [nameDraft, setNameDraft] = useState('')
  const [themeLabel, setThemeLabel] = useState('')
  const [showAvatarPicker, setShowAvatarPicker] = useState(false)

  const myPlayer = role === 'joueur' ? state.players.find((p) => p.id === localPlayerId) : undefined
  const myDisplayName = isPresenter ? state.presentateurName : (myPlayer?.name ?? null)
  const myAvatar = isPresenter ? state.presentateurAvatar : (myPlayer?.avatar ?? '')
  const canRenameSelf = isPresenter || Boolean(myPlayer)

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
    setShowAvatarPicker(false)
  }

  function handleAddTheme() {
    if (!themeLabel.trim()) return
    dispatch({ type: 'ADD_THEME', label: themeLabel })
    setThemeLabel('')
  }

  return (
    <ScreenShell spotlight smoke>
      <div className="flex flex-1 flex-col items-center justify-center gap-8 overflow-y-auto py-10">
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

        <div className="flex w-full max-w-md flex-col items-center gap-6">
          {/* Carte principale : code de room, présentateur, renommage, joueurs */}
          <div className="string-lights animate-rise-up relative w-full rounded-2xl border border-brass-600/30 bg-gradient-to-b from-charcoal-800 to-charcoal-900 p-6 shadow-stage-lg">
            <ArtDecoCorner position="top-left" />
            <ArtDecoCorner position="top-right" />
            <ArtDecoCorner position="bottom-left" />
            <ArtDecoCorner position="bottom-right" />

            {/* Code de room + Présentateur avec avatar */}
            <div className="mb-5 flex flex-col items-center gap-1">
              <span className="text-xs tracking-[0.3em] text-[#9a8d7d] uppercase">
                Code de la room
              </span>
              <span className="font-display text-3xl font-black tracking-[0.3em] text-amber-glow">
                {roomCode}
              </span>
              <div className="mt-2 flex items-center gap-2">
                {state.presentateurAvatar && (
                  <span className="text-2xl">{state.presentateurAvatar}</span>
                )}
                <span className="text-xs tracking-[0.2em] text-[#9a8d7d] uppercase">
                  Présentateur :{' '}
                  <span className="text-[#f1e6d8] normal-case">
                    {state.presentateurName ?? '…'}
                  </span>
                </span>
              </div>
            </div>

            {/* Identité de soi : renommage + choix avatar */}
            {canRenameSelf && (
              <div className="mb-5 flex flex-col gap-3 border-b border-white/5 pb-4">
                {/* Ligne pseudo */}
                <div className="flex items-center justify-center gap-2">
                  {editingSelf ? (
                    <>
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
                        className="flex-1 rounded-lg border border-brass-600/30 bg-charcoal-900/80 px-3 py-1.5 text-sm text-[#f1e6d8] outline-none focus:border-amber-glow"
                      />
                      <Button variant="primary" className="px-3 py-1.5 text-xs" onClick={confirmRename}>
                        Valider
                      </Button>
                    </>
                  ) : (
                    <>
                      {myAvatar && <span className="text-2xl">{myAvatar}</span>}
                      <span className="text-xs tracking-wide text-[#9a8d7d] uppercase">
                        Vous êtes{' '}
                        <span className="text-[#f1e6d8] normal-case">{myDisplayName}</span>
                      </span>
                      <button
                        onClick={startEditingSelf}
                        className="cursor-pointer text-xs tracking-wide text-amber-glow uppercase transition-colors hover:text-amber-ember"
                      >
                        Changer
                      </button>
                    </>
                  )}
                </div>

                {/* Sélecteur d'avatar */}
                <div className="flex flex-col items-center gap-2">
                  <button
                    onClick={() => setShowAvatarPicker((v) => !v)}
                    className="text-xs tracking-wide text-amber-glow uppercase transition-colors hover:text-amber-ember"
                  >
                    {showAvatarPicker ? 'Fermer le choix' : (myAvatar ? 'Changer mon icône' : 'Choisir mon icône')}
                  </button>
                  {showAvatarPicker && (
                    <div className="w-full rounded-xl border border-brass-600/20 bg-charcoal-900/80 p-3">
                      <AvatarPicker selected={myAvatar} onSelect={handleSelectAvatar} />
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Liste des joueurs avec leurs avatars */}
            {state.players.length > 0 ? (
              <ul className="flex flex-col gap-2">
                {state.players.map((player, i) => (
                  <li
                    key={player.id}
                    className="flex items-center justify-between rounded-lg border border-white/5 bg-charcoal-900/60 px-4 py-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
                  >
                    <div className="flex items-center gap-3">
                      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-charcoal-800 text-xl">
                        {player.avatar || '🎭'}
                      </span>
                      <div className="flex flex-col">
                        <span className="font-display text-lg text-[#f1e6d8]">{player.name}</span>
                        {!player.connected && (
                          <span className="text-xs text-[#7a6f63]">déconnecté</span>
                        )}
                      </div>
                    </div>
                    {isPresenter && (
                      <button
                        onClick={() => dispatch({ type: 'REMOVE_PLAYER', index: i })}
                        className="cursor-pointer text-xs tracking-wide text-burgundy-500 uppercase transition-colors hover:text-burgundy-500/70"
                      >
                        Retirer
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-center text-xs text-[#7a6f63]">
                Aucun joueur n'a encore rejoint la room.
              </p>
            )}

            {state.players.length < 2 && (
              <p className="mt-4 text-center text-xs text-[#7a6f63]">
                Minimum 2 joueurs requis pour lancer la partie.
              </p>
            )}
          </div>

        </div>

        {/* Panneau des thèmes — visible UNIQUEMENT par le Présentateur. */}
        {isPresenter && (
          <div className="animate-rise-up lg:fixed lg:right-4 lg:top-1/2 lg:-translate-y-1/2 w-full max-w-md lg:w-64 lg:max-w-none rounded-2xl border border-brass-600/30 bg-gradient-to-b from-charcoal-800 to-charcoal-900 p-5 shadow-stage-lg">
            <p className="mb-3 text-center text-xs tracking-[0.4em] text-brass-400/80 uppercase">
              ★ Thèmes ★
            </p>

            <div className="flex flex-col gap-2">
              <input
                type="text"
                value={themeLabel}
                onChange={(e) => setThemeLabel(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleAddTheme()
                }}
                placeholder="Nouveau thème"
                maxLength={30}
                className="w-full rounded-lg border border-brass-600/30 bg-charcoal-900/80 px-3 py-2 text-sm text-[#f1e6d8] placeholder-[#6b625b] shadow-[inset_0_2px_6px_rgba(0,0,0,0.4)] outline-none focus:border-amber-glow focus:shadow-[inset_0_2px_6px_rgba(0,0,0,0.4),0_0_0_3px_rgba(232,163,61,0.2)]"
              />
              <Button variant="primary" className="w-full" onClick={handleAddTheme} disabled={!themeLabel.trim()}>
                Ajouter
              </Button>
            </div>

              {state.themes.length > 0 && (
                <ul className="mt-5 flex max-h-64 flex-col gap-2 overflow-y-auto pr-1">
                  {state.themes.map((theme, i) => (
                    <li
                      key={i}
                      className="flex items-center justify-between rounded-lg border border-white/5 bg-charcoal-900/60 px-4 py-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
                    >
                      <span className="font-display text-sm text-[#f1e6d8]">{theme.label}</span>
                      <button
                        onClick={() => dispatch({ type: 'REMOVE_THEME', index: i })}
                        className="cursor-pointer text-xs tracking-wide text-burgundy-500 uppercase transition-colors hover:text-burgundy-500/70"
                      >
                        Retirer
                      </button>
                    </li>
                  ))}
                </ul>
              )}

            {state.themes.length < 1 && (
              <p className="mt-4 text-center text-xs text-[#7a6f63]">
                Minimum 1 thème requis pour lancer la partie.
              </p>
            )}
          </div>
        )}

        {isPresenter && (
          <Button
            variant="gold"
            className="animate-rise-up px-10 py-3 text-base"
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
    </ScreenShell>
  )
}
