"""Guthaben blueprint in admin panel"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
import pandas as pd

from models import db, Buchung, Mitglied
from utils.admin import calc_blacklist, export_df_to_excel
from datetime import datetime

guthaben_bp = Blueprint("guthaben", __name__, url_prefix="/guthaben")


@guthaben_bp.route("/", methods=["GET"])
@login_required
def guthaben_management():
    mitglieder = Mitglied.query.order_by(Mitglied.name).all()
    return render_template("admin/guthaben.html", mitglieder=mitglieder)


@guthaben_bp.route("/mitglied_blacklist_toggle/<int:mitglied_id>", methods=["POST"])
@login_required
def mitglied_blacklist_toggle(mitglied_id):
    data = request.get_json()
    mitglied = Mitglied.query.get_or_404(mitglied_id)
    mitglied.blacklist = bool(data.get("blacklist"))
    db.session.commit()
    return jsonify({"success": True, "blacklist": mitglied.blacklist})


@guthaben_bp.route("/guthaben_import", methods=["POST"])
@login_required
def guthaben_import():
    file = request.files.get("file")
    mitglied_col = request.form.get("mitglied_id_col", "id").strip()
    aufbuchung_col = request.form.get("aufbuchung_col", "betrag").strip()
    # FIX: beschreibung_col ist optional
    beschreibung_col = request.form.get("beschreibung_col", "").strip()

    if not file:
        flash("Keine Datei hochgeladen!", "error")
        return redirect(url_for("admin.guthaben.guthaben_management"))

    df = pd.read_excel(file)

    if mitglied_col not in df.columns or aufbuchung_col not in df.columns:
        flash("Pflicht-Spaltennamen nicht gefunden. Bitte überprüfe Mitglied-ID und Aufbuchung.", "error")
        return redirect(url_for("admin.guthaben.guthaben_management"))

    has_beschreibung = bool(beschreibung_col) and beschreibung_col in df.columns

    df = df[[mitglied_col, aufbuchung_col] + ([beschreibung_col] if has_beschreibung else [])].copy()
    df = df.dropna(subset=[mitglied_col, aufbuchung_col])
    df[mitglied_col] = pd.to_numeric(df[mitglied_col], errors="coerce")
    df[aufbuchung_col] = pd.to_numeric(df[aufbuchung_col], errors="coerce")
    df = df.dropna(subset=[mitglied_col, aufbuchung_col])

    if df.empty:
        flash("Keine gültigen Zeilen gefunden.", "error")
        return redirect(url_for("admin.guthaben.guthaben_management"))

    count = 0
    for _, row in df.iterrows():
        try:
            mitglied_id = int(row[mitglied_col])
            betrag = int(round(float(row[aufbuchung_col]) * 100, 0))
            beschreibung = str(row[beschreibung_col]) if has_beschreibung and row[beschreibung_col] is not None else None

            mitglied = Mitglied.query.get(mitglied_id)
            if mitglied:
                mitglied.blacklist = calc_blacklist(mitglied, betrag)
                mitglied.guthaben += betrag

                buchung = Buchung(
                    mitglied_id=mitglied.id,
                    artikel_id=None,
                    menge=1,
                    preis_pro_einheit=betrag,
                    gesamtpreis=betrag,
                    zeitstempel=datetime.now(),
                    beschreibung=beschreibung,
                    storno=False,
                )
                db.session.add(buchung)
                count += 1
        except Exception as e:
            print("Fehler bei Zeile:", e)

    db.session.commit()
    flash(f"{count} Guthabenänderungen durchgeführt.", "success")
    return redirect(url_for("admin.guthaben.guthaben_management"))


@guthaben_bp.route("/aufbuchung/<int:mitglied_id>", methods=["POST"])
@login_required
def aufbuchung(mitglied_id):
    data = request.get_json()
    betrag = data.get("betrag")
    beschreibung = data.get("beschreibung")
    if beschreibung is None or len(beschreibung) < 3:
        return jsonify({"success": False, "message": "Beschreibung fehlt oder ist zu kurz"}), 400

    if betrag is None:
        return jsonify({"success": False, "message": "Betrag fehlt"}), 400

    mitglied = Mitglied.query.get_or_404(mitglied_id)

    try:
        betrag_cent = int(round(float(betrag) * 100, 0))

        mitglied.blacklist = calc_blacklist(mitglied, betrag_cent)
        mitglied.guthaben += betrag_cent

        buchung = Buchung(
            mitglied_id=mitglied.id,
            artikel_id=None,
            menge=1,
            preis_pro_einheit=betrag_cent,
            gesamtpreis=betrag_cent,
            beschreibung=beschreibung,
            zeitstempel=datetime.now(),
        )
        db.session.add(buchung)
        db.session.add(mitglied)
        db.session.commit()

        flash(f"Guthaben von {mitglied.name} wurde geändert.", "success")
        return jsonify({"success": True})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
