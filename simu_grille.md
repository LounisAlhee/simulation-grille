# Simulation en direct de la grille USDG contre USDC (Kraken), sans argent

Écrit par `simu_grille.py`. Règles, jugement et prévision dans l'en-tête du script, écrits avant le premier relevé. Aucun ordre réel.

Début : 13/11/2026 17:10 UTC. Dernier relevé : 13/11/2026 17:20 UTC. Durée : 0,01 jours. Passages : 19. Carnet relevé 100 % du temps, 0 trous de plus de 10 minutes.

Transactions vues sur le marché : 18, pour 1036 USDG. Prix de départ 1,0001, dernier prix 1,0001.

| Compte | Gain depuis le début | Gain pour 200 USDC | Rythme annuel | Ordres servis | Allers-retours gagnants |
|---|---|---|---|---|---|
| tête de file | -0,0100 % | -0,020 USDC | trop tôt | 0 | 0 |
| file du carnet | -0,0100 % | -0,020 USDC | trop tôt | 0 | 0 |
| traversée | -0,0100 % | -0,020 USDC | trop tôt | 0 | 0 |

Le gain compte les lots encore ouverts à leur prix du jour et le coût de départ (0,02 % de la moitié achetée au marché, soit 0,020 USDC), que les trois comptes paient une fois.

Rythme annuel : gain depuis le début, ramené à un an sans intérêts composés. Il ne s'affiche qu'après 7 jours : avant, le coût de départ pèse trop.

Repères : Livret A 1,70 % par an. Garder moitié USDG, moitié USDC sans rien faire : -0,0100 % depuis le début.

File d'attente moyenne devant un ordre au moment où il est posé (compte « file du carnet ») : 210026 USDG, sur 10 ordres posés. Pire quantité vue : 80443 à l'achat, 1072492 à la vente.

## Jugement

Trop tôt. Lecture prévue le 11/02/2027, après 90 jours, si le carnet a été relevé au moins 80 % du temps.

Prévision de Claude écrite avant : « confirme » 70 chances sur 100, « au-dessus du Livret A » 15 chances sur 100.

## Limites

Aucun vrai ordre : les ordres cachés, l'effet d'un ordre réel sur les autres et l'accès depuis la France restent inconnus. Les annulations devant l'ordre ne font pas avancer la file (prudent). Carnet lu toutes les 30 secondes au mieux, pas en continu.
