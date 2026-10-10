/**
 * Rôle d'affichage LOCAL utilisé uniquement pour prévisualiser/tester les
 * différentes vues (Présentateur / Joueur / Écran principal) sur un seul
 * poste, en mode hotseat sans réseau (Bloc 7, partie faisable avant le
 * backend). Ceci n'est PAS une notion de rôle réseau : il n'y a ici qu'un
 * seul navigateur et un seul état de jeu partagé.
 *
 * TEMPORAIRE : sera remplacé au Bloc 7 réel (une fois le backend WebSocket
 * du Bloc 3 prêt) par un vrai routage par rôle décidé côté serveur de room,
 * où chaque device/joueur reçoit son propre rôle et ne voit que l'écran
 * correspondant — ce fichier et le sélecteur associé (RoleSwitcher) seront
 * alors supprimés.
 */
export type ViewRole = 'presentateur' | 'joueur' | 'ecran-principal'
