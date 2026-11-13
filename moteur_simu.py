"""Copie exacte du moteur à file d'attente du test 99 (classe GrilleFile de labo99.py), faite par
preparer_simu_github.py le 13/11/2026. Ne pas modifier ici."""
import grille7 as G7

H = 5
ATTENTE = 7
LIVRET_A = [('2006-08-01', 0.0275), ('2007-08-01', 0.03), ('2008-02-01', 0.035), ('2008-08-01', 0.04), ('2009-02-01', 0.025), ('2009-05-01', 0.0175), ('2009-08-01', 0.0125), ('2010-08-01', 0.0175), ('2011-02-01', 0.02), ('2011-08-01', 0.0225), ('2013-02-01', 0.0175), ('2013-08-01', 0.0125), ('2014-08-01', 0.01), ('2015-08-01', 0.0075), ('2019-01-01', 0.0075), ('2020-02-01', 0.005), ('2022-02-01', 0.01), ('2022-08-01', 0.02), ('2023-02-01', 0.03), ('2025-02-01', 0.024), ('2025-08-01', 0.017), ('2026-02-01', 0.015), ('2026-08-01', 0.017)]


class GrilleFile(G7.Grille7):
    """Grille en ticks, transaction par transaction, avec file d'attente (point 5 de la règle)."""

    def __init__(self, h, maker, cm, poids, sortie, V, mode, q0a, q0v):
        super().__init__(h, maker, cm, 0.0, poids, sortie, V)
        self.mode = mode
        self.q0a, self.q0v = (q0a, q0v) if mode in ("file", "file_v") else (0.0, 0.0)
        self.au_volume = mode.endswith("_v")
        self.ra, self.rv, self.ta, self.tv = [], [], [], []
        self.volume = 0.0

    def centrer(self, p):
        super().centrer(p)
        h, lv = self.h, self.lv
        self.ra = [self.q0a + self.cash[k] / lv[k] if k < h else 0.0 for k in range(self.nb)]
        self.rv = [0.0 if k < h else self.q0v + self.coin[k] for k in range(self.nb)]
        self.ta = [self.cash[k] / lv[k] if k < h else 0.0 for k in range(self.nb)]
        self.tv = [0.0 if k < h else self.coin[k] for k in range(self.nb)]

    def _vendre(self, k):
        lv, q, mk = self.lv, self.coin[k], self.maker
        brut = q * lv[k + 1]
        self.gains += q * (lv[k + 1] - self.achat[k])
        self.frais += brut * mk
        c = brut * (1 - mk)
        self.cycles += 1
        self.ordres += 1
        self.volume += q
        self.tq -= q
        self.tc += c
        self.coin[k], self.cash[k] = 0.0, c
        self.ra[k] = self.q0a + c / lv[k]
        self.ta[k] = c / lv[k]
        self.pos = k + 1

    def _acheter(self, k):
        lv, c, mk = self.lv, self.cash[k], self.maker
        self.frais += c * mk
        q = c * (1 - mk) / lv[k]
        self.ordres += 1
        self.volume += q
        self.tc -= c
        self.tq += q
        self.cash[k], self.coin[k], self.achat[k] = 0.0, q, lv[k]
        self.rv[k] = self.q0v + q
        self.tv[k] = q
        self.pos = k

    def transaction(self, p, v, s):
        nb, lv = self.nb, self.lv
        while not self.au_volume:
            pos = self.pos
            if pos < nb and p > lv[pos + 1]:
                self._vendre(pos)
            elif pos > 0 and p < lv[pos - 1]:
                self._acheter(pos - 1)
            else:
                break
        while self.au_volume and v > 0:      # point 12 : le volume au-delà du prix sert les ordres un par un
            pos = self.pos
            if pos < nb and p > lv[pos + 1]:
                if v >= self.tv[pos]:
                    v -= self.tv[pos]
                    self._vendre(pos)
                else:
                    self.tv[pos] -= v
                    v = 0.0
            elif pos > 0 and p < lv[pos - 1]:
                if v >= self.ta[pos - 1]:
                    v -= self.ta[pos - 1]
                    self._acheter(pos - 1)
                else:
                    self.ta[pos - 1] -= v
                    v = 0.0
            else:
                break
        if not self.mode.startswith("traversee"):
            pos = self.pos
            if s > 0:
                if pos < nb and p == lv[pos + 1]:
                    self.rv[pos] -= v
                    if self.rv[pos] <= 0:
                        self._vendre(pos)
            elif pos > 0 and p == lv[pos - 1]:
                self.ra[pos - 1] -= v
                if self.ra[pos - 1] <= 0:
                    self._acheter(pos - 1)
        pos = self.pos
        if pos == nb or pos == 0:
            if self.sortie == "recentre":
                self.recentrages += 1
                self.tc, self.tq = sum(self.cash), sum(self.coin)
                self.centrer(p)
                return
            if self.hors is None:
                self.hors = self.jour
        else:
            self.hors = None
        self._bornes()
