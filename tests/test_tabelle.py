"""Tests für das Tabellen-Makro templates/macros/tabelle.html."""

VORLAGE = """
{%- from "macros/tabelle.html" import tabelle, auswahl_zelle -%}
{% call tabelle("t", spalten, **optionen) %}
  <tr data-id="1">{% if optionen.auswahl %}{{ auswahl_zelle("ids", 1, checked=True) }}{% endif %}<td>Bier</td><td>2</td></tr>
{% endcall %}
"""


def render(app, spalten, **optionen):
    return app.jinja_env.from_string(VORLAGE).render(spalten=spalten, optionen=optionen)


def test_spaltenkoepfe_und_zeilen(app):
    html = render(app, ["Name", {"titel": "Menge", "klasse": "text-end"}])
    assert '<table class="table table-striped align-middle mb-0 table-hover" id="t">' in html
    assert ">Name</th>" in html
    assert '<th class="text-end" data-sort tabindex="0" aria-sort="none">Menge</th>' in html
    assert '<tr data-id="1">' in html
    assert "data-tabelle" in html


def test_ohne_suche_und_auswahl_keine_werkzeugleiste(app):
    html = render(app, ["Name"])
    assert "tabelle-werkzeuge" not in html
    assert "tabelle-suche" not in html
    assert "tabelle-alle" not in html


def test_suche(app):
    html = render(app, ["Name"], suche="Artikel suchen...")
    assert 'class="form-control tabelle-suche" placeholder="Artikel suchen..."' in html


def test_sortierung_abschaltbar(app):
    html = render(app, ["Name", {"titel": "Aktiv", "sort": False}])
    assert html.count("data-sort") == 1
    html = render(app, ["Name", "Menge"], sortierbar=False)
    assert "data-sort" not in html


def test_auswahl(app):
    html = render(app, ["Name"], auswahl=True)
    assert "tabelle-auswahl-kopf" in html
    assert "tabelle-alle" in html
    assert 'class="form-check-input tabelle-auswahl" name="ids" value="1"' in html
    assert "checked" in html


def test_hoehe_und_leertext(app):
    html = render(app, ["Name"], hoehe="70vh", leer="Nichts da.")
    assert "max-height:70vh" in html
    assert 'data-leer="Nichts da."' in html


def test_base_bindet_skript_ein(auth_client):
    html = auth_client.get("/admin/mitglied/").get_data(as_text=True)
    assert "js/tabelle.js" in html
