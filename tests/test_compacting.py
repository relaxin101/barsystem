"""Tests für Compacting (utils/compacting.py und blueprints/admin/compacting.py)."""
import io
from datetime import datetime

import pandas as pd
import pytest
from sqlalchemy import func

from models import Abrechnung, Artikel, Buchung, Mitglied
from utils.compacting import abrechnungen_im_zeitraum, parse_zeitraum, plane
from utils.zeit import LOCAL_TZ

BIS = "2025-03-31T23:59"


def lokal(*args):
    return datetime(*args, tzinfo=LOCAL_TZ)


def buchen(db, mitglied, betrag, ts, abrechnung=None, artikel=None, storno=False):
    b = Buchung(
        mitglied_id=mitglied.id,
        artikel_id=artikel.id if artikel else None,
        abrechnungs_id=abrechnung.id if abrechnung else None,
        beschreibung=None if artikel else "Aufbuchung",
        menge=1,
        preis_pro_einheit=abs(betrag),
        gesamtpreis=betrag,
        zeitstempel=ts,
        storno=storno,
    )
    db.session.add(b)
    return b


@pytest.fixture()
def daten(db):
    """A1 liegt ganz im März, A2 ragt in den April, eine Buchung ohne Abrechnung im März."""
    anna = Mitglied(name="Anna", guthaben=250)
    bert = Mitglied(name="Bert", guthaben=0, aktiv=False)
    carl = Mitglied(name="Carl", guthaben=-600)
    dora = Mitglied(name="Dora", guthaben=0, aktiv=True)  # nie gebucht
    emil = Mitglied(name="Emil", guthaben=500)  # nie gebucht, aber Guthaben
    bier = Artikel(name="Bier", preis=250)
    wein = Artikel(name="Wein", preis=300)
    alt = Artikel(name="Altbier", preis=200, aktiv=False)
    a1 = Abrechnung(name="März", zeitstempel=lokal(2025, 4, 1, 12))
    a2 = Abrechnung(name="März/April", zeitstempel=lokal(2025, 4, 20, 12))
    db.session.add_all([anna, bert, carl, dora, emil, bier, wein, alt, a1, a2])
    db.session.flush()

    buchen(db, anna, 1000, lokal(2025, 3, 1, 20), a1)
    buchen(db, anna, -250, lokal(2025, 3, 1, 23), a1, bier)
    buchen(db, anna, -250, lokal(2025, 3, 2, 2), a1, bier)   # derselbe Bar-Abend
    buchen(db, anna, -250, lokal(2025, 3, 2, 19), a1, bier)  # neuer Abend
    buchen(db, bert, 250, lokal(2025, 3, 5, 20), a1)
    buchen(db, bert, -250, lokal(2025, 3, 5, 21), a1, bier)
    buchen(db, carl, -250, lokal(2025, 3, 6, 21), a1, bier, storno=True)
    buchen(db, carl, -300, lokal(2025, 3, 28, 21), a2, wein)
    buchen(db, carl, -300, lokal(2025, 4, 2, 21), a2, wein)
    buchen(db, anna, 0, lokal(2025, 3, 10, 21))  # ohne Abrechnung
    db.session.commit()
    return dict(anna=anna, bert=bert, carl=carl, dora=dora, emil=emil,
                bier=bier, wein=wein, alt=alt, a1=a1, a2=a2)


def summen():
    return dict(
        Buchung.query.with_entities(Buchung.mitglied_id, func.sum(Buchung.gesamtpreis))
        .filter(Buchung.storno == False)  # noqa: E712
        .group_by(Buchung.mitglied_id)
    )


def formular(d, fingerprint, artikel=(), mitglied=(), purge=True, von="", bis=BIS):
    data = {"von": von, "bis": bis, "fingerprint": fingerprint,
            "artikel": [str(i) for i in artikel], "mitglied": [str(i) for i in mitglied]}
    if purge:
        data.update(purge_artikel="1", purge_mitglieder="1")
    return data


def fingerprint(bis=BIS):
    return plane(*parse_zeitraum("", bis)).fingerprint


# ------------------------------------------------
# Zeitraum und Zuordnung
# ------------------------------------------------
def test_parse_zeitraum_offen_und_ganze_minute():
    assert parse_zeitraum("", "") == (None, None)
    von, bis = parse_zeitraum("2025-03-01T00:00", "2025-03-31T23:59")
    assert von == lokal(2025, 3, 1)
    assert bis == lokal(2025, 3, 31, 23, 59, 59, 999999)


def test_zuordnung_enthalten_und_durchtrennt(daten):
    enthalten, durchtrennt = abrechnungen_im_zeitraum(*parse_zeitraum("", BIS))
    assert [i.abrechnung.name for i in enthalten] == ["März"]
    assert [i.abrechnung.name for i in durchtrennt] == ["März/April"]


def test_zuordnung_nach_oben_offen(daten):
    enthalten, durchtrennt = abrechnungen_im_zeitraum(*parse_zeitraum("2025-01-01T00:00", ""))
    assert {i.abrechnung.name for i in enthalten} == {"März", "März/April"}
    assert durchtrennt == []


def test_zuordnung_ausserhalb_weder_noch(daten):
    enthalten, durchtrennt = abrechnungen_im_zeitraum(*parse_zeitraum("2025-05-01T00:00", "2025-06-01T00:00"))
    assert enthalten == [] and durchtrennt == []


# ------------------------------------------------
# Plan
# ------------------------------------------------
def test_plan_salden_und_kandidaten(daten):
    plan = plane(*parse_zeitraum("", BIS))
    d = daten
    assert len(plan.buchungen) == 7
    # Bert gleicht sich aus, Carls einzige Buchung im Set ist storniert
    assert plan.salden == {d["anna"].id: 250}
    # Wein steckt noch in A2; Altbier war nie gebucht
    assert {a.name for a in plan.artikel} == {"Bier", "Altbier"}
    assert {m.name for m in plan.mitglieder} == {"Bert", "Dora", "Emil"}
    # Aktiv spielt keine Rolle, Guthaben schon
    assert plan.mitglieder_loeschbar == {d["bert"].id, d["dora"].id}
    assert plan.lose_buchungen == 1
    assert plan.name == "Compacting 01.03.2025–06.03.2025"


# ------------------------------------------------
# Ausführen
# ------------------------------------------------
def test_ausfuehren(superuser_client, db, daten):
    d = daten
    vorher = summen()
    a1_id, a2_id = d["a1"].id, d["a2"].id
    ids = {k: d[k].id for k in ("anna", "bert", "dora", "emil", "bier", "alt", "wein")}

    resp = superuser_client.post("/admin/compacting/ausfuehren", data=formular(
        d, fingerprint(), artikel=[ids["bier"], ids["alt"]], mitglied=[ids["bert"], ids["dora"]]))
    assert resp.status_code == 200
    assert resp.mimetype.endswith("spreadsheetml.sheet")
    assert resp.headers["X-Weiter"].startswith("/admin/abrechnung/")

    db.session.expire_all()
    assert db.session.get(Abrechnung, a1_id) is None
    assert db.session.get(Abrechnung, a2_id) is not None
    neu = Abrechnung.query.filter(Abrechnung.name.like("Compacting%")).one()
    zeilen = Buchung.query.filter_by(abrechnungs_id=neu.id).all()
    assert [(b.mitglied_id, b.gesamtpreis, b.artikel_id) for b in zeilen] == [(ids["anna"], 250, None)]
    assert zeilen[0].zeitstempel == lokal(2025, 3, 6, 21)

    # Summe pro Mitglied unverändert (gelöschte Mitglieder hatten Summe 0)
    nachher = summen()
    assert {m: s for m, s in vorher.items() if s} == {m: s for m, s in nachher.items() if s}
    assert db.session.get(Mitglied, ids["anna"]).guthaben == 250

    assert db.session.get(Artikel, ids["bier"]) is None
    assert db.session.get(Artikel, ids["alt"]) is None
    assert db.session.get(Artikel, ids["wein"]) is not None
    assert db.session.get(Mitglied, ids["bert"]) is None
    assert db.session.get(Mitglied, ids["dora"]) is None
    assert db.session.get(Mitglied, ids["emil"]) is not None
    assert Buchung.query.filter_by(abrechnungs_id=None).count() == 1


def test_ohne_purge_wird_nichts_geloescht(superuser_client, db, daten):
    d = daten
    resp = superuser_client.post("/admin/compacting/ausfuehren", data=formular(
        d, fingerprint(), artikel=[d["bier"].id], mitglied=[d["bert"].id], purge=False))
    assert resp.status_code == 200
    assert Artikel.query.count() == 3
    assert Mitglied.query.count() == 5


def test_fingerprint_abweichung(superuser_client, db, daten):
    d = daten
    alt = fingerprint()
    buchen(db, d["anna"], -250, lokal(2025, 3, 3, 21), d["a1"], d["bier"])
    db.session.commit()

    resp = superuser_client.post("/admin/compacting/ausfuehren", data=formular(d, alt))
    assert resp.status_code == 409
    assert "geändert" in resp.get_json()["message"]
    assert db.session.get(Abrechnung, d["a1"].id) is not None


def test_mitglied_mit_guthaben_nicht_loeschbar(superuser_client, db, daten):
    d = daten
    resp = superuser_client.post("/admin/compacting/ausfuehren", data=formular(
        d, fingerprint(), mitglied=[d["emil"].id]))
    assert resp.status_code == 409
    assert db.session.get(Mitglied, d["emil"].id) is not None
    assert db.session.get(Abrechnung, d["a1"].id) is not None


def test_ohne_abrechnung_im_zeitraum(superuser_client, daten):
    resp = superuser_client.post("/admin/compacting/ausfuehren", data=formular(
        daten, fingerprint("2025-01-31T23:59"), bis="2025-01-31T23:59"))
    assert resp.status_code == 409


# ------------------------------------------------
# Bericht
# ------------------------------------------------
def test_bericht(superuser_client, daten):
    resp = superuser_client.post("/admin/compacting/bericht", data=formular(daten, ""))
    assert resp.status_code == 200
    blaetter = pd.read_excel(io.BytesIO(resp.data), sheet_name=None, header=None)
    assert list(blaetter) == ["Übersicht", "Mitglieder"]

    kennzahlen = dict(blaetter["Übersicht"].iloc[1:12, :2].values)
    assert kennzahlen["Summe Aufbuchungen (€)"] == 12.5
    assert kennzahlen["Summe Abbuchungen (€)"] == 10  # Carls Storno zählt nicht
    assert kennzahlen["davon Artikelumsatz (€)"] == 10
    assert kennzahlen["davon storniert"] == 1

    mitglieder = pd.read_excel(io.BytesIO(resp.data), sheet_name="Mitglieder").set_index("Name")
    assert list(mitglieder.index) == ["Anna", "Bert"]
    assert mitglieder.loc["Anna", "Tage"] == 2  # 23:00 und 02:00 sind ein Abend
    assert mitglieder.loc["Anna", "Bier"] == 3
    assert mitglieder.loc["Anna", "Summe auf (€)"] == 10
    assert mitglieder.loc["Anna", "Summe ab (€)"] == 7.5


# ------------------------------------------------
# Seiten und Rechte
# ------------------------------------------------
def test_seiten_rendern(superuser_client, daten):
    assert superuser_client.get("/admin/compacting/").status_code == 200

    resp = superuser_client.get(f"/admin/compacting/vorschau?von=&bis={BIS}")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "März/April" in html  # als durchtrennt angezeigt
    assert 'name="artikel"' in html and 'name="mitglied"' in html

    resp = superuser_client.post("/admin/compacting/pruefen", data=formular(daten, "", mitglied=[daten["bert"].id]))
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "ragt über den Zeitraum hinaus" in html
    assert fingerprint() in html
    ausfuehren_btn = html.split('id="ausfuehren-btn"')[1].split(">")[0]
    assert "disabled" not in ausfuehren_btn

    # Emil hat Guthaben: Fehler, Ausführen gesperrt
    resp = superuser_client.post("/admin/compacting/pruefen", data=formular(daten, "", mitglied=[daten["emil"].id]))
    html = resp.get_data(as_text=True)
    assert "alert-danger" in html
    assert "disabled" in html.split('id="ausfuehren-btn"')[1].split(">")[0]


def test_zurueck_behaelt_auswahl(superuser_client, daten):
    d = daten
    resp = superuser_client.get(
        f"/admin/compacting/vorschau?bis={BIS}&zurueck=1&artikel={d['alt'].id}")
    html = resp.get_data(as_text=True)
    assert f'value="{d["alt"].id}"\n         checked' in html
    assert f'value="{d["bier"].id}"\n         checked' not in html


@pytest.mark.parametrize("methode,url", [
    ("get", "/admin/compacting/"),
    ("get", "/admin/compacting/vorschau"),
    ("post", "/admin/compacting/pruefen"),
    ("post", "/admin/compacting/bericht"),
    ("post", "/admin/compacting/ausfuehren"),
])
def test_nur_superuser(auth_client, methode, url):
    assert getattr(auth_client, methode)(url).status_code == 403
