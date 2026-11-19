"""Compacting im Adminpanel (nur Superuser): Zeitraum wählen, prüfen, Bericht, ausführen."""

from flask import Blueprint, flash, jsonify, render_template, request, send_file, url_for

from utils.admin import superuser_required
from utils.compacting import (
    ausfuehren as compacting_ausfuehren,
    bericht_dateiname,
    bericht_xlsx,
    konflikte,
    parse_zeitraum,
    plane,
)

compacting_bp = Blueprint("compacting", __name__, url_prefix="/compacting")

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _parameter(quelle):
    """Liest Zeitraum, Purge-Schalter und Auswahl aus request.args oder request.form."""
    von, bis = quelle.get("von", "").strip(), quelle.get("bis", "").strip()
    purge_artikel = quelle.get("purge_artikel") == "1"
    purge_mitglieder = quelle.get("purge_mitglieder") == "1"
    # Die Auswahl reist immer mit (für "Zurück"), gelöscht wird nur bei aktivem Schalter
    artikel_auswahl = quelle.getlist("artikel", type=int)
    mitglied_auswahl = quelle.getlist("mitglied", type=int)
    return {
        "von": von,
        "bis": bis,
        "purge_artikel": purge_artikel,
        "purge_mitglieder": purge_mitglieder,
        "artikel_auswahl": artikel_auswahl,
        "mitglied_auswahl": mitglied_auswahl,
        "artikel_ids": artikel_auswahl if purge_artikel else [],
        "mitglied_ids": mitglied_auswahl if purge_mitglieder else [],
    }


def _plan(p):
    try:
        von, bis = parse_zeitraum(p["von"], p["bis"])
    except ValueError:
        return None
    return plane(von, bis)


@compacting_bp.route("/")
@superuser_required
def index():
    return render_template("admin/compacting/index.html")


@compacting_bp.route("/vorschau")
@superuser_required
def vorschau():
    p = _parameter(request.args)
    plan = _plan(p)
    if plan is None:
        flash("Ungültiger Zeitraum.", "error")
        return render_template("admin/compacting/index.html"), 400

    # Erster Aufruf: alles Löschbare vorausgewählt; nach "Zurück" die mitgeschickte Auswahl
    zurueck = request.args.get("zurueck") == "1"
    artikel_auswahl = set(p["artikel_auswahl"]) if zurueck else plan.artikel_loeschbar
    mitglied_auswahl = set(p["mitglied_auswahl"]) if zurueck else plan.mitglieder_loeschbar

    return render_template(
        "admin/compacting/vorschau.html",
        plan=plan,
        p=p,
        artikel_auswahl=artikel_auswahl,
        mitglied_auswahl=mitglied_auswahl,
    )


@compacting_bp.route("/pruefen", methods=["POST"])
@superuser_required
def pruefen():
    p = _parameter(request.form)
    plan = _plan(p)
    if plan is None:
        flash("Ungültiger Zeitraum.", "error")
        return render_template("admin/compacting/index.html"), 400

    fehler, warnungen = konflikte(plan, p["artikel_ids"], p["mitglied_ids"])
    artikel_ids, mitglied_ids = set(p["artikel_ids"]), set(p["mitglied_ids"])
    return render_template(
        "admin/compacting/pruefen.html",
        plan=plan,
        p=p,
        fehler=fehler,
        warnungen=warnungen,
        artikel=[a for a in plan.artikel if a.id in artikel_ids],
        mitglieder=[m for m in plan.mitglieder if m.id in mitglied_ids],
    )


@compacting_bp.route("/bericht", methods=["POST"])
@superuser_required
def bericht():
    plan = _plan(_parameter(request.form))
    if plan is None:
        flash("Ungültiger Zeitraum.", "error")
        return render_template("admin/compacting/index.html"), 400
    return send_file(bericht_xlsx(plan), as_attachment=True, download_name=bericht_dateiname(plan), mimetype=XLSX)


@compacting_bp.route("/ausfuehren", methods=["POST"])
@superuser_required
def ausfuehren():
    p = _parameter(request.form)
    plan = _plan(p)
    if plan is None:
        return jsonify(success=False, message="Ungültiger Zeitraum."), 400

    if request.form.get("fingerprint") != plan.fingerprint:
        return jsonify(
            success=False,
            message="Die Buchungen haben sich seit der Prüfung geändert. Bitte erneut prüfen.",
        ), 409

    fehler, _ = konflikte(plan, p["artikel_ids"], p["mitglied_ids"])
    if fehler:
        return jsonify(success=False, message=" ".join(fehler)), 409

    # Bericht vor dem Löschen erzeugen, danach fehlen die Einzelbuchungen
    bericht = bericht_xlsx(plan)
    dateiname = bericht_dateiname(plan)
    anzahl_buchungen, anzahl_salden = len(plan.buchungen), len(plan.salden)
    neu, geloeschte_artikel, geloeschte_mitglieder = compacting_ausfuehren(
        plan, p["artikel_ids"], p["mitglied_ids"]
    )

    flash(
        f'Compacting abgeschlossen: {anzahl_buchungen} Buchungen zu {anzahl_salden} Saldo-Zeilen '
        f'in Abrechnung "{neu.name}" zusammengefasst, {geloeschte_artikel} Artikel und '
        f"{geloeschte_mitglieder} Mitglieder gelöscht.",
        "success",
    )
    response = send_file(bericht, as_attachment=True, download_name=dateiname, mimetype=XLSX)
    response.headers["X-Weiter"] = url_for("admin.abrechnung.detail", abrechnung_id=neu.id)
    return response
