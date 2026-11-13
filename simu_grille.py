"""Simulation en direct, sans argent, de la grille USDG contre USDC de Kraken (suite du test 99).

Demande du 13/11/2026 : faire tourner le seul bot gagnant du labo en simulation sur le vrai carnet.
Règles, jugement et prévision écrits le 13/11/2026, avant le premier relevé. Aucun ordre, aucun compte,
aucune clé : le script lit le carnet et les transactions publics de Kraken et fait comme si ses ordres
étaient posés.

Ce que la simulation ajoute au test 99. Le test 99 plaçait chaque ordre derrière une file d'attente fixe,
relevée une seule fois le 11/11/2026 (815 000 unités à l'achat, 29 000 à la vente). Ici, chaque ordre passe
derrière la quantité réellement affichée à son prix au moment où il est posé. C'est la meilleure mesure
possible de la place dans la file sans passer un vrai ordre.

Règle rejouée, sans rien changer : la variante retenue à l'étape 1 du test 99. Moteur `GrilleFile` de
`labo99.py`. Pas de 1 cran de prix (0,0001), 5 bandes de chaque côté, pause hors zone (la grille attend et
ne se relance que si le prix reste dehors 7 jours), 0 % de frais en ordre limité, 0,02 % pour la moitié
achetée au marché au départ (0,01 % de frais plus un cran). Sens des transactions : celui de Kraken, sans
inversion (le test 99 a montré que c'est le bon sur cette paire).
Capital simulé : 200 USDC, soit des lots d'environ 20 unités.

Trois comptes tournent en même temps sur les mêmes transactions :
  tête de file : l'ordre est servi dès que les transactions faites à son prix atteignent sa taille (borne
     favorable, pour information) ;
  file du carnet : l'ordre attend derrière la quantité affichée à son prix quand il est posé ; cette file ne
     fond qu'avec les transactions faites à ce prix (les annulations devant lui ne comptent pas : prudent) ;
  traversée : l'ordre n'est servi que si une transaction se fait au-delà de son prix (borne dure).
Entre deux relevés du carnet, la file retenue pour un ordre posé est la plus grande des deux quantités
affichées (avant et après). Après un trou de plus de 10 minutes sans relevé (Mac éteint, script arrêté), les
transactions manquées sont rejouées en entier (Kraken les garde toutes), mais les ordres posés pendant le
trou passent derrière la plus grosse quantité jamais vue de ce côté du carnet : le pire cas.

Jugement, fixé avant. Lecture le 11/02/2027, après 90 jours. Elle ne compte que si le carnet a été relevé
au moins 80 % du temps (sinon : « mesure insuffisante »).
  « Confirme le test 99 » si le gain est positif en file du carnet ET en traversée.
  « Au-dessus du Livret A » si, en plus, le gain annualisé en file du carnet dépasse le taux du Livret A.
  Sinon « ne confirme pas ».
Un « confirme » n'est pas une victoire : il resterait ce que seul un vrai ordre montre (ordres cachés,
effet de son propre ordre sur les autres, accès depuis la France).

Prévision de Claude, avant le premier relevé : « confirme » 70 chances sur 100, « au-dessus du Livret A »
15 chances sur 100. Ordre de grandeur attendu : 1 à 2 % par an, soit 20 à 35 centimes par mois pour 200 USDC.

Usage :
  python3 simu_grille.py controle      contrôle du moteur, sans réseau
  python3 simu_grille.py               un passage : rattrape les transactions, relève le carnet, écrit le rapport
  python3 simu_grille.py --boucle 30   un passage toutes les 30 secondes, jusqu'à Ctrl-C
  python3 simu_grille.py --boucle 30 --duree 20400   la même boucle, arrêtée après 20 400 secondes (GitHub)
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

try:
    import moteur_simu as L99   # dépôt GitHub : copie exacte du moteur, faite par preparer_simu_github.py
except ImportError:
    import labo99 as L99

ICI =os.path.dirname(os.path.abspath(__file__))
DOSSIER = os.path.join(ICI, "donnees", "simu_grille")
ETAT = os.path.join(DOSSIER, "etat.json")
JOURNAL = os.path.join(DOSSIER, "journal.csv")
RAPPORT = os.path.join(ICI, "simu_grille.md")

PAIRE = "USDGUSDC"
TICK = 0.0001
CAPITAL = 200.0
V0 = CAPITAL / TICK
CM = 0.0002
MODES = ["tete", "file", "traversee"]
NOM = {"tete": "tête de file", "file": "file du carnet", "traversee": "traversée"}
TROU_S = 600
DEBUT_PREVU, LECTURE = "13/11/2026", "2027-02-11"
COUVERTURE_MIN = 0.80

CARNET = {"a": {}, "v": {}}     # quantités affichées par prix (en crans) : a = achat, v = vente
FAITS = []                      # ordres servis pendant le passage en cours


class GrilleDirect(L99.GrilleFile):
    """Le moteur du test 99, avec la file d'attente lue dans le carnet au moment où l'ordre est posé."""

    def _file(self, cote, niveau):
        if self.mode != "file":
            return 0.0
        q = CARNET[cote].get(int(round(niveau)), 0.0)
        self.poses += 1
        self.somme_files += q
        return q

    def centrer(self, p):
        super().centrer(p)
        h, lv = self.h, self.lv
        self.ra = [self._file("a", lv[k]) + self.cash[k] / lv[k] if k < h else 0.0 for k in range(self.nb)]
        self.rv = [0.0 if k < h else self._file("v", lv[k + 1]) + self.coin[k] for k in range(self.nb)]

    def _vendre(self, k):
        q, prix = self.coin[k], self.lv[k + 1]
        super()._vendre(k)
        self.ra[k] = self._file("a", self.lv[k]) + self.ta[k]
        FAITS.append((self.t_cours, self.mode, "vente", prix, q))

    def _acheter(self, k):
        c, prix = self.cash[k], self.lv[k]
        super()._acheter(k)
        self.rv[k] = self._file("v", self.lv[k + 1]) + self.tv[k]
        FAITS.append((self.t_cours, self.mode, "achat", prix, c / prix))


def lire(url, essais=4):
    err = None
    for i in range(essais):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "python-urllib"})
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode())
            if d.get("error"):
                raise RuntimeError(str(d["error"]))
            return d["result"]
        except Exception as e:  # réseau ou quota : on attend et on réessaie
            err = e
            time.sleep(3 * (i + 1))
    raise RuntimeError("Kraken ne répond pas : %s" % err)


def transactions(depuis):
    """Toutes les transactions après le curseur. Rend (liste, nouveau curseur)."""
    out = []
    while True:
        url = "https://api.kraken.com/0/public/Trades?pair=%s" % PAIRE + ("&since=%s" % depuis if depuis else "")
        res = lire(url)
        page = next(v for k, v in res.items() if k != "last")
        if depuis:
            out.extend(page)
        elif page:
            out.append(page[-1])           # premier passage : seulement le dernier prix
        if not depuis or len(page) < 1000 or res["last"] == depuis:
            return out, res["last"]
        depuis = res["last"]
        time.sleep(1.1)


def carnet():
    res = lire("https://api.kraken.com/0/public/Depth?pair=%s&count=25" % PAIRE)
    d = next(iter(res.values()))
    lit = lambda cote: {int(round(float(p) / TICK)): float(q) for p, q, _ in d[cote]}
    return {"a": lit("bids"), "v": lit("asks")}


def nouveau_compte(mode):
    st = GrilleDirect(L99.H, 0.0, CM, None, "pause", V0, mode, 0.0, 0.0)
    st.pas_abs = 1
    st.poses, st.somme_files, st.t_cours, st.jour = 0, 0.0, 0.0, 0
    return st


def charger():
    if not os.path.exists(ETAT):
        return None
    with open(ETAT) as f:
        e = json.load(f)
    comptes = {}
    for m in MODES:
        st = nouveau_compte(m)
        st.__dict__.update(e["comptes"][m])
        comptes[m] = st
    e["comptes"] = comptes
    return e


def sauver(e):
    brut = dict(e, comptes={m: st.__dict__ for m, st in e["comptes"].items()})
    with open(ETAT + ".tmp", "w") as f:
        json.dump(brut, f)
    os.replace(ETAT + ".tmp", ETAT)


def jour_nouveau(st, j, prix):
    """Règle de la pause : relance si le prix est resté hors de la grille 7 jours (comme `simuler_k`)."""
    if j != st.jour:
        if st.actif and st.hors is not None and j - st.hors >= L99.ATTENTE:
            st.recentrages += 1
            st.centrer(prix)
        st.jour = j


def passage():
    global CARNET
    os.makedirs(DOSSIER, exist_ok=True)
    e = charger()
    maintenant = time.time()
    if e is None:
        tr, curseur = transactions(None)
        if not tr:
            raise RuntimeError("aucune transaction lue, impossible de démarrer")
        prix = int(round(float(tr[-1][0]) / TICK))
        CARNET = carnet()
        comptes = {m: nouveau_compte(m) for m in MODES}
        for st in comptes.values():
            st.jour = int(maintenant // 86400)
            st.centrer(prix)
        e = {"debut": maintenant, "prix0": prix, "curseur": curseur, "prix": prix, "dernier": maintenant,
             "couvert": 0.0, "passages": 0, "transactions": 0, "volume": 0.0, "trous": 0, "carnet": CARNET,
             "pire": {c: max(CARNET[c].values()) for c in "av"}, "valeurs": {}, "comptes": comptes}
    else:
        tr, e["curseur"] = transactions(e["curseur"])
        neuf = carnet()
        trou = maintenant - e["dernier"] > TROU_S
        pire = e["pire"]
        for c in "av":
            pire[c] = max(pire[c], max(neuf[c].values()))
        if trou:
            e["trous"] += 1
            CARNET = {c: _Pire(pire[c]) for c in "av"}
        else:
            e["couvert"] += maintenant - e["dernier"]
            avant = {c: {int(k): v for k, v in e["carnet"][c].items()} for c in "av"}
            CARNET = {c: {p: max(avant[c].get(p, 0.0), neuf[c].get(p, 0.0)) for p in set(avant[c]) | set(neuf[c])}
                      for c in "av"}
        for t in tr:
            p, v, quand, s = int(round(float(t[0]) / TICK)), float(t[1]), float(t[2]), 1 if t[3] == "b" else -1
            for st in e["comptes"].values():
                jour_nouveau(st, int(quand // 86400), e["prix"])
                st.t_cours = quand
                st.transaction(p, v, s)
            e["prix"] = p
            e["transactions"] += 1
            e["volume"] += v
        CARNET = neuf
        for st in e["comptes"].values():
            jour_nouveau(st, int(maintenant // 86400), e["prix"])
        e["carnet"] = neuf
        e["dernier"] = maintenant
    e["passages"] += 1
    jour = datetime.fromtimestamp(maintenant, timezone.utc).strftime("%Y-%m-%d")
    e["valeurs"][jour] = {m: st.valeur(e["prix"]) / V0 for m, st in e["comptes"].items()}
    if FAITS:
        neuf_fichier = not os.path.exists(JOURNAL)
        with open(JOURNAL, "a") as f:
            if neuf_fichier:
                f.write("heure_utc;compte;sens;prix;quantite\n")
            for quand, mode, sens, prix, q in FAITS:
                f.write("%s;%s;%s;%.4f;%.3f\n" % (datetime.fromtimestamp(quand, timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S"), mode, sens, prix * TICK, q))
        del FAITS[:]
    sauver(e)
    rapport(e)
    return e


class _Pire(dict):
    """Carnet du pire cas : tout prix, même absent, porte la plus grosse quantité jamais vue."""

    def __init__(self, pire):
        super().__init__()
        self.pire = pire

    def get(self, k, defaut=None):
        return self.pire


def controle():
    """Contrôle écrit avant le premier relevé : sur des transactions tirées au hasard, le compte « file du
    carnet » doit redonner la tête de file avec un carnet vide, et la traversée avec une file immense."""
    global CARNET
    import random
    rnd = random.Random(99)
    p, tr = 10000, []
    for _ in range(20000):
        p += rnd.choice((-1, 0, 0, 1))
        tr.append((p, rnd.uniform(1, 500), rnd.choice((1, -1))))
    res = {}
    for nom, livre in (("vide", {"a": {}, "v": {}}), ("immense", {c: _Pire(1e15) for c in "av"})):
        CARNET = livre
        comptes = {m: nouveau_compte(m) for m in MODES}
        for st in comptes.values():
            st.centrer(10000)
            for prix, v, s in tr:
                st.transaction(prix, v, s)
        res[nom] = {m: (round(st.valeur(p), 6), st.ordres) for m, st in comptes.items()}
    del FAITS[:]
    ok1 = res["vide"]["file"] == res["vide"]["tete"]
    ok2 = res["immense"]["file"] == res["immense"]["traversee"]
    ok3 = res["vide"]["tete"][1] > res["vide"]["traversee"][1] > 0
    print("carnet vide : file = tête de file : %s %s" % (ok1, res["vide"]["file"]))
    print("file immense : file = traversée : %s %s" % (ok2, res["immense"]["file"]))
    print("la tête de file sert plus d'ordres que la traversée : %s (%d contre %d)"
          % (ok3, res["vide"]["tete"][1], res["vide"]["traversee"][1]))
    return ok1 and ok2 and ok3


def nombre(x, d=2):
    return ("%+.*f" % (d, x)).replace(".", ",")


def rapport(e):
    maintenant = e["dernier"]
    jours = max((maintenant - e["debut"]) / 86400, 1e-9)
    couverture = e["couvert"] / max(maintenant - e["debut"], 1e-9)
    livret = L99.LIVRET_A[-1][1]
    fmt = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%d/%m/%Y %H:%M")
    L = []
    w = L.append
    w("# Simulation en direct de la grille USDG contre USDC (Kraken), sans argent")
    w("")
    w("Écrit par `simu_grille.py`. Règles, jugement et prévision dans l'en-tête du script, écrits avant le"
      " premier relevé. Aucun ordre réel.")
    w("")
    w("Début : %s UTC. Dernier relevé : %s UTC. Durée : %s jours. Passages : %d. Carnet relevé %d %% du temps,"
      " %d trous de plus de 10 minutes."
      % (fmt(e["debut"]), fmt(maintenant), ("%.2f" % jours).replace(".", ","), e["passages"],
         round(100 * couverture), e["trous"]))
    w("")
    w("Transactions vues sur le marché : %d, pour %d USDG. Prix de départ %s, dernier prix %s."
      % (e["transactions"], round(e["volume"]), ("%.4f" % (e["prix0"] * TICK)).replace(".", ","),
         ("%.4f" % (e["prix"] * TICK)).replace(".", ",")))
    w("")
    w("| Compte | Gain depuis le début | Gain pour 200 USDC | Rythme annuel | Ordres servis | Allers-retours gagnants |")
    w("|---|---|---|---|---|---|")
    gains = {}
    for m in MODES:
        st = e["comptes"][m]
        g = st.valeur(e["prix"]) / V0 - 1
        gains[m] = g
        rythme = nombre(100 * g * 365.25 / jours) + " %" if jours >= 7 else "trop tôt"
        w("| %s | %s %% | %s USDC | %s | %d | %d |"
          % (NOM[m], nombre(100 * g, 4), nombre(CAPITAL * g, 3), rythme, st.ordres, st.cycles))
    w("")
    w("Le gain compte les lots encore ouverts à leur prix du jour et le coût de départ (0,02 %% de la moitié"
      " achetée au marché, soit %s USDC), que les trois comptes paient une fois." % nombre(CAPITAL / 2 * CM, 3).replace("+", ""))
    w("")
    w("Rythme annuel : gain depuis le début, ramené à un an sans intérêts composés. Il ne s'affiche qu'après"
      " 7 jours : avant, le coût de départ pèse trop.")
    w("")
    w("Repères : Livret A %s %% par an. Garder moitié USDG, moitié USDC sans rien faire : %s %% depuis le début."
      % (nombre(100 * livret).replace("+", ""), nombre(100 * (0.5 * e["prix"] / e["prix0"] - 0.5 - CM / 2), 4)))
    st = e["comptes"]["file"]
    if st.poses:
        w("")
        w("File d'attente moyenne devant un ordre au moment où il est posé (compte « file du carnet ») : %d USDG,"
          " sur %d ordres posés. Pire quantité vue : %d à l'achat, %d à la vente."
          % (round(st.somme_files / st.poses), st.poses, round(e["pire"]["a"]), round(e["pire"]["v"])))
    w("")
    w("## Jugement")
    w("")
    if datetime.fromtimestamp(maintenant, timezone.utc).strftime("%Y-%m-%d") < LECTURE:
        w("Trop tôt. Lecture prévue le 11/02/2027, après 90 jours, si le carnet a été relevé au moins 80 % du temps.")
    elif couverture < COUVERTURE_MIN:
        w("**Mesure insuffisante** : le carnet n'a été relevé que %d %% du temps." % round(100 * couverture))
    elif gains["file"] > 0 and gains["traversee"] > 0:
        dessus = gains["file"] * 365.25 / jours > livret
        w("**Confirme le test 99%s.**" % (", au-dessus du Livret A" if dessus else ", sous le Livret A"))
    else:
        w("**Ne confirme pas le test 99.**")
    w("")
    w("Prévision de Claude écrite avant : « confirme » 70 chances sur 100, « au-dessus du Livret A » 15 chances sur 100.")
    w("")
    w("## Limites")
    w("")
    w("Aucun vrai ordre : les ordres cachés, l'effet d'un ordre réel sur les autres et l'accès depuis la France"
      " restent inconnus. Les annulations devant l'ordre ne font pas avancer la file (prudent). Carnet lu toutes"
      " les 30 secondes au mieux, pas en continu.")
    w("")
    with open(RAPPORT, "w") as f:
        f.write("\n".join(L))


def main():
    if "controle" in sys.argv:
        sys.exit(0 if controle() else 1)
    if "--boucle" in sys.argv:
        i = sys.argv.index("--boucle")
        pause = float(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 30.0
        print("Simulation en boucle, un passage toutes les %d secondes. Ctrl-C pour arrêter." % pause, flush=True)
        fin = (time.time() + float(sys.argv[sys.argv.index("--duree") + 1])) if "--duree" in sys.argv else None
        while fin is None or time.time() < fin:
            try:
                e = passage()
                if e["passages"] % 20 == 1:
                    print("%s passages %d, ordres servis %s" % (time.strftime("%d/%m %H:%M"), e["passages"], {
                        m: st.ordres for m, st in e["comptes"].items()}), flush=True)
            except KeyboardInterrupt:
                break
            except Exception as err:  # une panne réseau ne doit pas arrêter la boucle
                print("%s passage raté : %s" % (time.strftime("%d/%m %H:%M"), err), flush=True)
            try:
                time.sleep(pause)
            except KeyboardInterrupt:
                break
    else:
        e = passage()
        print("Passage %d fait. Ordres servis : %s. Rapport : simu_grille.md" % (e["passages"], {
            m: st.ordres for m, st in e["comptes"].items()}))


if __name__ == "__main__":
    main()
