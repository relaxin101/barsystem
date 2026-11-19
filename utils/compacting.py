"""Compacting: ganze Abrechnungen eines Zeitraums zu einer Saldo-Zeile pro Mitglied zusammenfassen.

Die Summe der Buchungen eines Mitglieds bleibt dabei gleich, Mitglied.guthaben
muss also nicht angefasst werden. Stornierte Buchungen fallen weg, sie haben
das Guthaben nie verändert.
"""

import io
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import func, or_, true

from models import db, Abrechnung, Artikel, Buchung, Mitglied
from utils.zeit import LOCAL_TZ, naive_local, parse_local, parse_local_ende, utcnow

# Ein Bar-Abend endet erst am Morgen: 23:00 und 02:00 zählen als derselbe Tag
TAGESWECHSEL = timedelta(hours=6)
# Saldo-Zeilen jünger als das tauchen in Hotlist und Aussendungs-Statistiken auf
WARN_TAGE = 30


@dataclass
class AbrechnungsInfo:
    abrechnung: Abrechnung
    von: datetime | None
    bis: datetime | None
    anzahl: int
    veraendert: bool


@dataclass
class Plan:
    von: datetime | None
    bis: datetime | None
    abrechnungen: list[AbrechnungsInfo]
    durchtrennt: list[AbrechnungsInfo]
    buchungen: list[Buchung]
    salden: dict[int, int]
    artikel: list[Artikel]
    mitglieder: list[Mitglied]
    lose_buchungen: int
    abweichungen: list[tuple[Mitglied, int]] = field(default_factory=list)

    @property
    def gueltige(self):
        return [b for b in self.buchungen if not b.storno]

    @property
    def erste(self):
        return self.buchungen[0].zeitstempel if self.buchungen else None

    @property
    def stich(self):
        return self.buchungen[-1].zeitstempel if self.buchungen else None

    @property
    def artikel_loeschbar(self):
        return {a.id for a in self.artikel}

    @property
    def mitglieder_loeschbar(self):
        return {m.id for m in self.mitglieder if m.guthaben == 0}

    @property
    def fingerprint(self):
        """Ändert sich, sobald im Set eine Buchung dazukommt, wegfällt oder storniert wird."""
        return "{}:{}:{}:{}".format(
            len(self.buchungen),
            sum(b.gesamtpreis for b in self.buchungen),
            max((b.id for b in self.buchungen), default=0),
            sum(b.storno for b in self.buchungen),
        )

    @property
    def name(self):
        if not self.buchungen:
            return "Compacting"
        return "Compacting {:%d.%m.%Y}–{:%d.%m.%Y}".format(
            self.erste.astimezone(LOCAL_TZ), self.stich.astimezone(LOCAL_TZ)
        )


# ------------------------------------------------
# Zeitraum und Abrechnungen
# ------------------------------------------------
def parse_zeitraum(von, bis):
    """Formularwerte (datetime-local) zu Ortszeit; leer heißt offen."""
    return (parse_local(von) if von else None), (parse_local_ende(bis) if bis else None)


def abrechnungen_im_zeitraum(von, bis):
    """Teilt Abrechnungen in (enthalten, durchtrennt).

    Enthalten heißt: alle Buchungen liegen im Zeitraum. Eine leere Abrechnung
    zählt über ihren eigenen Zeitstempel.
    """
    spannen = {
        row.id: row
        for row in db.session.query(
            Buchung.abrechnungs_id.label("id"),
            func.min(Buchung.zeitstempel).label("von"),
            func.max(Buchung.zeitstempel).label("bis"),
            func.count(Buchung.id).label("anzahl"),
            func.max(Buchung.storno_updated_at).label("storno"),
        )
        .filter(Buchung.abrechnungs_id.isnot(None))
        .group_by(Buchung.abrechnungs_id)
    }

    enthalten, durchtrennt = [], []
    for a in Abrechnung.query.order_by(Abrechnung.zeitstempel, Abrechnung.id):
        s = spannen.get(a.id)
        lo, hi = (s.von, s.bis) if s else (a.zeitstempel, a.zeitstempel)
        info = AbrechnungsInfo(
            abrechnung=a,
            von=s.von if s else None,
            bis=s.bis if s else None,
            anzahl=s.anzahl if s else 0,
            veraendert=bool(s and s.storno and s.storno > a.zeitstempel),
        )
        ab_von = von is None or lo >= von
        bis_ende = bis is None or hi <= bis
        if ab_von and bis_ende:
            enthalten.append(info)
        elif (von is None or hi >= von) and (bis is None or lo <= bis):
            durchtrennt.append(info)
    return enthalten, durchtrennt


def plane(von, bis):
    enthalten, durchtrennt = abrechnungen_im_zeitraum(von, bis)
    ids = [i.abrechnung.id for i in enthalten]

    buchungen = (
        Buchung.query.filter(Buchung.abrechnungs_id.in_(ids))
        .order_by(Buchung.zeitstempel, Buchung.id)
        .all()
        if ids else []
    )

    salden = defaultdict(int)
    for b in buchungen:
        if not b.storno:
            salden[b.mitglied_id] += b.gesamtpreis
    salden = {m: s for m, s in salden.items() if s != 0}

    # NOT IN allein ließe Buchungen ohne Abrechnung (NULL) weg
    ausserhalb = (
        or_(Buchung.abrechnungs_id.is_(None), Buchung.abrechnungs_id.notin_(ids))
        if ids else true()
    )
    artikel_ref = {
        a for (a,) in db.session.query(Buchung.artikel_id)
        .filter(ausserhalb, Buchung.artikel_id.isnot(None)).distinct()
    }
    mitglied_ref = {
        m for (m,) in db.session.query(Buchung.mitglied_id).filter(ausserhalb).distinct()
    } | set(salden)

    artikel = Artikel.query.filter(Artikel.id.notin_(artikel_ref)).order_by(Artikel.name).all()
    mitglieder = Mitglied.query.filter(Mitglied.id.notin_(mitglied_ref)).order_by(Mitglied.name).all()

    lose = Buchung.query.filter(Buchung.abrechnungs_id.is_(None))
    if von is not None:
        lose = lose.filter(Buchung.zeitstempel >= von)
    if bis is not None:
        lose = lose.filter(Buchung.zeitstempel <= bis)

    return Plan(
        von=von,
        bis=bis,
        abrechnungen=enthalten,
        durchtrennt=durchtrennt,
        buchungen=buchungen,
        salden=salden,
        artikel=artikel,
        mitglieder=mitglieder,
        lose_buchungen=lose.count(),
        abweichungen=_guthaben_abweichungen({b.mitglied_id for b in buchungen}),
    )


def _guthaben_abweichungen(mitglied_ids):
    """Mitglieder, deren Guthaben nicht der Summe ihrer gültigen Buchungen entspricht."""
    if not mitglied_ids:
        return []
    summen = dict(
        db.session.query(Buchung.mitglied_id, func.sum(Buchung.gesamtpreis))
        .filter(Buchung.mitglied_id.in_(mitglied_ids), Buchung.storno == False)  # noqa: E712
        .group_by(Buchung.mitglied_id)
    )
    return [
        (m, m.guthaben - summen.get(m.id, 0))
        for m in Mitglied.query.filter(Mitglied.id.in_(mitglied_ids)).order_by(Mitglied.name)
        if m.guthaben != summen.get(m.id, 0)
    ]


# ------------------------------------------------
# Prüfungen
# ------------------------------------------------
def konflikte(plan, artikel_ids, mitglied_ids):
    """Gibt (fehler, warnungen) zurück. Bei Fehlern darf nicht ausgeführt werden."""
    fehler, warnungen = [], []

    if plan.von and plan.bis and plan.von > plan.bis:
        fehler.append("Der Beginn des Zeitraums liegt nach dem Ende.")
    if not plan.abrechnungen:
        fehler.append("Im Zeitraum liegt keine vollständige Abrechnung.")
    if set(artikel_ids) - plan.artikel_loeschbar:
        fehler.append("Ausgewählte Artikel sind danach noch referenziert oder existieren nicht mehr.")
    if set(mitglied_ids) - plan.mitglieder_loeschbar:
        fehler.append(
            "Ausgewählte Mitglieder sind danach noch referenziert, haben Guthaben "
            "oder existieren nicht mehr."
        )

    for i in plan.durchtrennt:
        warnungen.append(
            f'Abrechnung {i.abrechnung.id} "{i.abrechnung.name}" ragt über den Zeitraum hinaus '
            "und bleibt unverändert."
        )
    if plan.lose_buchungen:
        warnungen.append(
            f"{plan.lose_buchungen} Buchung(en) im Zeitraum gehören zu keiner Abrechnung "
            "und bleiben unverändert."
        )
    for i in plan.abrechnungen:
        if i.veraendert:
            warnungen.append(
                f'Abrechnung {i.abrechnung.id} "{i.abrechnung.name}" hat sich nach der Abrechnung '
                "durch Stornos verändert. Compacting verwendet den aktuellen Stand."
            )
    for m, diff in plan.abweichungen:
        warnungen.append(
            f"Guthaben von {m.name} weicht um € {diff / 100:.2f} von der Summe der Buchungen ab. "
            "Die Abweichung bleibt erhalten."
        )
    if plan.stich and plan.stich > utcnow() - timedelta(days=WARN_TAGE):
        warnungen.append(
            f"Der Zeitraum endet in den letzten {WARN_TAGE} Tagen: Saldo-Zeilen können in "
            "Hotlist und Aussendungs-Statistiken auftauchen."
        )
    return fehler, warnungen


# ------------------------------------------------
# Bericht
# ------------------------------------------------
def _euro(cent):
    return round(cent / 100, 2)


def _bar_tag(zeitstempel):
    return (zeitstempel.astimezone(LOCAL_TZ) - TAGESWECHSEL).date()


def bericht_xlsx(plan):
    gueltig = plan.gueltige
    auf = sum(b.gesamtpreis for b in gueltig if b.gesamtpreis > 0)
    ab_artikel = -sum(b.gesamtpreis for b in gueltig if b.gesamtpreis < 0 and b.artikel_id)
    ab_sonst = -sum(b.gesamtpreis for b in gueltig if b.gesamtpreis < 0 and not b.artikel_id)

    def zeit(value):
        return naive_local(value) if value else "offen"

    uebersicht = pd.DataFrame(
        [
            ("Zeitraum von", zeit(plan.von)),
            ("Zeitraum bis", zeit(plan.bis)),
            ("Erste Buchung", naive_local(plan.erste) if plan.erste else ""),
            ("Letzte Buchung (Stichzeitpunkt)", naive_local(plan.stich) if plan.stich else ""),
            ("Buchungen gesamt", len(plan.buchungen)),
            ("davon storniert", len(plan.buchungen) - len(gueltig)),
            ("Summe Aufbuchungen (€)", _euro(auf)),
            ("Summe Abbuchungen (€)", _euro(ab_artikel + ab_sonst)),
            ("davon Artikelumsatz (€)", _euro(ab_artikel)),
            ("davon sonstige Belastungen (€)", _euro(ab_sonst)),
            ("Saldo (€)", _euro(auf - ab_artikel - ab_sonst)),
        ],
        columns=["Kennzahl", "Wert"],
    )

    abrechnungen = pd.DataFrame(
        [
            {
                "ID": i.abrechnung.id,
                "Name": i.abrechnung.name,
                "Abrechnungszeitpunkt": naive_local(i.abrechnung.zeitstempel),
                "Buchungen von": naive_local(i.von),
                "Buchungen bis": naive_local(i.bis),
                "Anzahl Buchungen": i.anzahl,
            }
            for i in plan.abrechnungen
        ],
        columns=["ID", "Name", "Abrechnungszeitpunkt", "Buchungen von", "Buchungen bis", "Anzahl Buchungen"],
    )

    produkte = {}
    for b in gueltig:
        if b.artikel_id:
            p = produkte.setdefault(b.artikel_id, {"ID": b.artikel_id, "Artikel": b.artikel_obj.name, "Menge": 0, "cent": 0})
            p["Menge"] += b.menge
            p["cent"] -= b.gesamtpreis
    produkte = sorted(produkte.values(), key=lambda p: p["Artikel"])
    artikel_df = pd.DataFrame(
        [{"ID": p["ID"], "Artikel": p["Artikel"], "Menge": p["Menge"], "Umsatz (€)": _euro(p["cent"])} for p in produkte],
        columns=["ID", "Artikel", "Menge", "Umsatz (€)"],
    )

    konten = {}
    for b in gueltig:
        k = konten.setdefault(b.mitglied_id, {"m": b.mitglied_obj, "auf": 0, "ab": 0, "tage": set(), "menge": defaultdict(int)})
        if b.gesamtpreis > 0:
            k["auf"] += b.gesamtpreis
        else:
            k["ab"] -= b.gesamtpreis
        if b.artikel_id:
            k["tage"].add(_bar_tag(b.zeitstempel))
            k["menge"][b.artikel_id] += b.menge
    mitglieder_df = pd.DataFrame(
        [
            {
                "ID": k["m"].id,
                "Name": k["m"].name,
                "Nickname": k["m"].nickname or "",
                "Summe auf (€)": _euro(k["auf"]),
                "Summe ab (€)": _euro(k["ab"]),
                "Tage": len(k["tage"]),
                **{p["Artikel"]: k["menge"].get(p["ID"], 0) for p in produkte},
            }
            for k in sorted(konten.values(), key=lambda k: k["m"].name.lower())
        ],
        columns=["ID", "Name", "Nickname", "Summe auf (€)", "Summe ab (€)", "Tage"] + [p["Artikel"] for p in produkte],
    )

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter", datetime_format="dd.mm.yyyy hh:mm") as writer:
        uebersicht.to_excel(writer, sheet_name="Übersicht", index=False)
        zeile = len(uebersicht) + 2
        abrechnungen.to_excel(writer, sheet_name="Übersicht", index=False, startrow=zeile)
        zeile += len(abrechnungen) + 2
        artikel_df.to_excel(writer, sheet_name="Übersicht", index=False, startrow=zeile)
        mitglieder_df.to_excel(writer, sheet_name="Mitglieder", index=False)

        writer.sheets["Übersicht"].set_column(0, 0, 32)
        writer.sheets["Übersicht"].set_column(1, 5, 20)
        writer.sheets["Mitglieder"].set_column(1, 2, 24)
    buf.seek(0)
    return buf


def bericht_dateiname(plan):
    if not plan.buchungen:
        return "compacting.xlsx"
    return "compacting_{:%Y-%m-%d}_{:%Y-%m-%d}.xlsx".format(
        plan.erste.astimezone(LOCAL_TZ), plan.stich.astimezone(LOCAL_TZ)
    )


# ------------------------------------------------
# Ausführen
# ------------------------------------------------
def ausfuehren(plan, artikel_ids, mitglied_ids):
    """Ersetzt die Buchungen des Plans durch Saldo-Zeilen und löscht die gewählten Stammdaten.

    Die Prüfung über konflikte() muss vorher gelaufen sein. Referenzen werden hier
    trotzdem noch einmal in derselben Transaktion geprüft.
    """
    neu = Abrechnung(name=plan.name)
    db.session.add(neu)
    db.session.flush()

    beschreibung = f"Compacting-Saldo {plan.name.removeprefix('Compacting ')}"
    for mitglied_id, saldo in plan.salden.items():
        db.session.add(Buchung(
            mitglied_id=mitglied_id,
            artikel_id=None,
            abrechnungs_id=neu.id,
            beschreibung=beschreibung,
            menge=1,
            preis_pro_einheit=saldo,
            gesamtpreis=saldo,
            zeitstempel=plan.stich,
            storno=False,
        ))

    buchung_ids = [b.id for b in plan.buchungen]
    abrechnung_ids = [i.abrechnung.id for i in plan.abrechnungen]
    db.session.flush()
    Buchung.query.filter(Buchung.id.in_(buchung_ids)).delete(synchronize_session=False)
    Abrechnung.query.filter(Abrechnung.id.in_(abrechnung_ids)).delete(synchronize_session=False)

    artikel_ids = _ohne_referenz(Buchung.artikel_id, artikel_ids)
    mitglied_ids = [
        m for (m,) in db.session.query(Mitglied.id).filter(
            Mitglied.id.in_(_ohne_referenz(Buchung.mitglied_id, mitglied_ids)),
            Mitglied.guthaben == 0,
        )
    ]
    Artikel.query.filter(Artikel.id.in_(artikel_ids)).delete(synchronize_session=False)
    Mitglied.query.filter(Mitglied.id.in_(mitglied_ids)).delete(synchronize_session=False)

    db.session.commit()
    db.session.expire_all()
    return neu, len(artikel_ids), len(mitglied_ids)


def _ohne_referenz(spalte, ids):
    if not ids:
        return []
    referenziert = {r for (r,) in db.session.query(spalte).filter(spalte.in_(ids)).distinct()}
    return [i for i in ids if i not in referenziert]
