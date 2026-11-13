"""Lot 7 : moteur de grille du test 99 (grille au contact du test 92, plus les protections de la voie G3).

Écrit le 11/11/2026 avant tout téléchargement d'un marché nouveau. Contrôle écrit avant : sans protection, sans
marge et avec un pas de 1 %, le moteur doit redonner les chiffres du test 92 sur BTC (borne prudente -28,6 % par
an, borne favorable -4,9 % par an). Usage : python3 notes-lot7/grille7.py   (lance ce contrôle)

Vocabulaire
- Une bande est l'espace entre deux niveaux voisins. Chaque bande tient soit des dollars (ordre d'achat posé à
  son niveau bas), soit des pièces (ordre de vente posé à son niveau haut).
- Marge : 0 pour un ordre rempli dès que le prix touche son niveau (« au contact ») ; un tick pour un ordre rempli
  seulement si le prix dépasse son niveau d'au moins un tick (« traversée » : on est en fin de file d'attente).
- Sortie « recentre » : quand toutes les bandes sont du même côté, la grille se relance à 50/50 autour du prix
  (test 90). Sortie « pause » : la grille attend ; elle ne se relance que si le prix reste dehors D jours.
- Arrêt : si le prix descend d'une demi-hauteur de grille sous le bas de la grille, tout est vendu au marché et le
  bot attend D jours avant de repartir.
- Filtre de tendance : le bot ne tourne que si la clôture de la veille est au-dessus de sa moyenne des N derniers
  jours ; sinon tout est en dollars.
- Poids : part du capital de chaque bande, du centre vers le bord (égaux, ou plus petits aux bords).
- Pas glissant : le pas est recalculé chaque jour sur la variation quotidienne médiane des 30 derniers jours.
"""
import sys
from pathlib import Path

INF = float("inf")


class Grille7:
    def __init__(self, h, maker, cm, marge=0.0, poids=None, sortie="recentre", V=1.0):
        self.h, self.nb = h, 2 * h
        self.maker, self.cm, self.marge = maker, cm, marge
        self.w = poids or [1.0 / h] * h
        self.sortie = sortie
        self.ordres = self.recentrages = self.cycles = self.arrets = 0
        self.gains = self.frais = 0.0          # gains bruts des cycles fermés, frais payés (en monnaie)
        self.tc, self.tq = V, 0.0
        self.actif = False
        self.hors = None                       # jour où le prix est sorti de la grille (sortie « pause »)
        self.reprise = None                    # jour de reprise après un arrêt
        self.pas_abs = None                    # pas fixe en unité de prix (marchés en ticks)
        self.g = None                          # pas en part du prix
        self.jour = 0
        self.cash, self.coin, self.achat, self.lv, self.pos = [], [], [], [], 0
        self.haut, self.bas, self.stop = INF, -INF, -INF

    def copie(self):
        c = object.__new__(Grille7)
        c.__dict__.update(self.__dict__)
        c.cash, c.coin, c.achat = self.cash[:], self.coin[:], self.achat[:]
        return c

    def valeur(self, p):
        return self.tc + self.tq * p

    def _bornes(self):
        pos, lv, m = self.pos, self.lv, self.marge
        self.haut = lv[pos + 1] + m if pos < self.nb else INF
        self.bas = lv[pos - 1] - m if pos > 0 else -INF

    def centrer(self, p):
        """Lance ou relance la grille autour de p avec toute la valeur ; l'écart à 50/50 s'échange au marché."""
        V = self.tc + self.tq * p
        cout = abs(V / 2 - self.tq * p) * self.cm
        self.frais += cout
        V -= cout
        h, nb, w = self.h, self.nb, self.w
        pas = self.pas_abs if self.pas_abs else self.g * p
        self.lv = [p + (k - h) * pas for k in range(nb + 1)]
        self.cash = [V / 2 * w[h - k - 1] if k < h else 0.0 for k in range(nb)]
        self.coin = [0.0 if k < h else V / 2 * w[k - h] / p for k in range(nb)]
        self.achat = [0.0 if k < h else p for k in range(nb)]
        self.pos = h
        self.tc, self.tq = V / 2, V / 2 / p
        self.actif, self.hors, self.reprise = True, None, None
        self.stop = self.lv[0] - h * pas
        self._bornes()

    def vendre_tout(self, p):
        """Tout en dollars, au marché, au prix p."""
        brut = self.tq * p
        self.frais += brut * self.cm
        # les lots vendus sont comptés hors « cycles fermés » : c'est une sortie forcée
        self.tc += brut * (1 - self.cm)
        self.tq = 0.0
        self.cash, self.coin = [], []
        self.actif = False
        self.haut, self.bas, self.stop = INF, -INF, -INF

    def avancer(self, p):
        if not self.actif:
            return
        nb, mk, m = self.nb, self.maker, self.marge
        while True:
            lv, cash, coin, achat, pos = self.lv, self.cash, self.coin, self.achat, self.pos
            while pos < nb and p >= lv[pos + 1] + m:
                brut = coin[pos] * lv[pos + 1]
                self.gains += coin[pos] * (lv[pos + 1] - achat[pos])
                self.frais += brut * mk
                c = brut * (1 - mk)
                self.cycles += 1
                self.tq -= coin[pos]
                coin[pos], cash[pos] = 0.0, c
                self.tc += c
                pos += 1
                self.ordres += 1
            while pos > 0 and p <= lv[pos - 1] - m:
                k = pos - 1
                self.frais += cash[k] * mk
                qte = cash[k] * (1 - mk) / lv[k]
                self.tc -= cash[k]
                cash[k], coin[k], achat[k] = 0.0, qte, lv[k]
                self.tq += qte
                pos -= 1
                self.ordres += 1
            self.pos = pos
            if pos == nb or pos == 0:
                if self.sortie == "recentre":
                    self.recentrages += 1
                    q = lv[nb] + m if pos == nb else lv[0] - m
                    # recalcul exact des totaux, comme le test 92
                    self.tc, self.tq = sum(cash), sum(coin)
                    self.centrer(q)
                    continue
                if self.hors is None:
                    self.hors = self.jour
            else:
                self.hors = None
            self._bornes()
            return


def pas_minute(st, hi, lo, c, favorable):
    """Une minute. L'ordre du haut et du bas est inconnu : on garde le pire (borne prudente) ou le meilleur."""
    if hi < st.haut and lo > st.bas:
        return st
    a = st.copie()
    a.avancer(hi)
    a.avancer(lo)
    a.avancer(c)
    st.avancer(lo)
    st.avancer(hi)
    st.avancer(c)
    if favorable == (a.valeur(c) > st.valeur(c)):
        return a
    return st


def simuler(Hi, Lo, C, idx, d0, d1, clot, regl, favorable):
    """Du jour d0 au jour d1 inclus. idx : {jour: (i0, i1)} ; clot : {jour: clôture}.
    regl : dict avec h, maker, cm, marge, poids, sortie, pas_abs ou g, et en option
    arret (bool), attente (jours), tendance (N jours), pas_glissant (multiple de la variation médiane, 30 jours).
    Renvoie ({jour: valeur}, état)."""
    st = Grille7(regl["h"], regl["maker"], regl["cm"], regl["marge"], regl.get("poids"), regl.get("sortie", "recentre"))
    st.pas_abs, st.g = regl.get("pas_abs"), regl.get("g")
    arret, attente = regl.get("arret", False), regl.get("attente", 7)
    tendance, glissant = regl.get("tendance"), regl.get("pas_glissant")
    hist = [clot[j] for j in sorted(clot) if j < d0]      # clôtures d'avant d0, pour moyenne et pas glissant
    vals, last = {}, None
    for j in range(d0, d1 + 1):
        r = idx.get(j)
        if r is None:
            if last is not None:
                vals[j] = st.valeur(last)
            continue
        i0, i1 = r
        st.jour = j
        p_ouv = last if last is not None else C[i0]
        # décisions prises à 00 h 00 avec les clôtures connues
        if glissant and len(hist) > 30:
            var = sorted(abs(hist[k] / hist[k - 1] - 1) for k in range(len(hist) - 30, len(hist)))
            med = (var[14] + var[15]) / 2
            if med > 0:
                st.g = glissant * med
        feu_vert = True
        if tendance:
            feu_vert = len(hist) >= tendance and hist[-1] > sum(hist[-tendance:]) / tendance
        if st.actif and not feu_vert:
            st.vendre_tout(p_ouv)
        elif not st.actif and feu_vert and (st.reprise is None or j >= st.reprise) and (st.g or st.pas_abs):
            st.centrer(p_ouv)
        elif st.actif and st.sortie == "pause" and st.hors is not None and j - st.hors >= attente:
            st.recentrages += 1
            st.centrer(p_ouv)
        haut, bas, stop = st.haut, st.bas, st.stop if arret else -INF
        for i in range(i0, i1):
            hi = Hi[i]
            lo = Lo[i]
            if hi < haut and lo > bas:
                continue
            if lo <= stop:
                st.avancer(stop)
                st.arrets += 1
                st.vendre_tout(stop)
                st.reprise = j + attente
            else:
                st = pas_minute(st, hi, lo, C[i], favorable)
            haut, bas, stop = st.haut, st.bas, st.stop if arret else -INF
        last = C[i1 - 1]
        hist.append(last)
        vals[j] = st.valeur(last)
    return vals, st


def controle():
    """Le moteur redonne-t-il le test 92 sur BTC ?"""
    ici = Path(__file__).resolve().parent
    sys.path.insert(0, str(ici.parent))
    import labo92
    import labo94
    J, Hi, Lo, C = labo92.charger("BTCUSDT")
    idx = labo94.index_jours(J)
    clot = {j: C[i1 - 1] for j, (i0, i1) in idx.items()}
    ans = (J[-1] - J[0] + 1) / 365.25
    ok = True
    for favorable, attendu in ((False, -28.6), (True, -4.9)):
        regl = {"h": 5, "maker": 0.0008, "cm": 0.0010 + 0.0002, "marge": 0.0, "g": 0.01}
        vals, st = simuler(Hi, Lo, C, idx, J[0], J[-1], clot, regl, favorable)
        v = vals[J[-1]]
        an = (v ** (1 / ans) - 1) * 100
        print(f"BTC {'favorable' if favorable else 'prudente'} : {an:+.1f} % par an (test 92 : {attendu:+.1f} %), "
              f"{st.ordres} ordres, {st.recentrages} recentrages, gains des cycles {st.gains:.3f}, frais {st.frais:.3f}")
        ok = ok and abs(an - attendu) < 0.6
    print("contrôle", "réussi" if ok else "ÉCHOUÉ")


if __name__ == "__main__":
    controle()
