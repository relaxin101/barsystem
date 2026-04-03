"""Guthaben blueprint in admin panel"""

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
)
from flask_login import login_required
import pandas as pd

from models import db, Buchung, Mitglied
from utils.admin import *
from config import MINDEST_GUTHABEN

guthaben_bp = Blueprint("guthaben", __name__, url_prefix="/guthaben")

# --------------------------------
# 💶 Guthaben Management
# --------------------------------
@guthaben_bp.route("/", methods=["GET"])
@login_required
def guthaben_management():
    mitglieder = Mitglied.query.order_by(Mitglied.name).all()
    return render_template("admin/guthaben.html", mitglieder=mitglieder)


# 🧮 Toggle Blacklist
@guthaben_bp.route("/mitglied_blacklist_toggle/<int:mitglied_id>", methods=["POST"])
@login_required
def mitglied_blacklist_toggle(mitglied_id):
    data = request.get_json()
    mitglied = Mitglied.query.get_or_404(mitglied_id)
    mitglied.blacklist = bool(data.get("blacklist"))
    db.session.commit()
    return jsonify({"success": True, "blacklist": mitglied.blacklist})


# 📤 Excel Import für Guthabenänderungen
@guthaben_bp.route("/guthaben_import", methods=["POST"])
@login_required
def guthaben_import():
    file = request.files.get("file")
    mitglied_col = request.form.get("mitglied_id_col")
    aufbuchung_col = request.form.get("aufbuchung_col")

    if not file:
        flash("Keine Datei hochgeladen!", "error")
        return redirect(url_for("admin.guthaben.guthaben_management"))

    # Excel einlesen
    df = pd.read_excel(file)

    # Prüfen, ob die Spalten existieren
    if mitglied_col not in df.columns or aufbuchung_col not in df.columns:
        flash("Spaltennamen nicht gefunden. Bitte überprüfe die Zuordnung.", "error")
        return redirect(url_for("admin.guthaben.guthaben_management"))

    # Nur Zeilen behalten, wo BEIDE Werte numerisch und nicht leer sind
    df = df[[mitglied_col, aufbuchung_col]].copy()
    df = df.dropna(subset=[mitglied_col, aufbuchung_col])

    # Versuch, die Werte in Zahlen umzuwandeln (nicht konvertierbare werden NaN)
    df[mitglied_col] = pd.to_numeric(df[mitglied_col], errors="coerce")
    df[aufbuchung_col] = pd.to_numeric(df[aufbuchung_col], errors="coerce")

    # Nur Zeilen mit gültigen Zahlen behalten
    df = df.dropna(subset=[mitglied_col, aufbuchung_col])

    if df.empty:
        flash(
            "Keine gültigen Zeilen gefunden (beide Spalten müssen Zahlen enthalten).",
            "error",
        )
        return redirect(url_for("admin.guthaben.guthaben_management"))

    count = 0
    for _, row in df.iterrows():
        try:
            mitglied_id = int(row[mitglied_col])
            betrag = int(float(row[aufbuchung_col])*100)
            mitglied = Mitglied.query.get(mitglied_id)
            print(row)
            if mitglied:
                mitglied.guthaben += betrag

                if mitglied.guthaben < MINDEST_GUTHABEN*100:
                    mitglied.blacklist = True
                elif mitglied.guthaben > MINDEST_GUTHABEN*100:
                    mitglied.blacklist = False

                buchung = Buchung(
                    mitglied_id=mitglied.id,
                    artikel_id=None,  # oder Dummy
                    menge=1,
                    preis_pro_einheit=-betrag,
                    gesamtpreis=-betrag,
                    zeitstempel=datetime.now(),
                    storniert=None,
                )
                db.session.add(buchung)
                count += 1
        except Exception as e:
            print("Fehler bei Zeile:", e)

    db.session.commit()
    flash(f"{count} Guthabenänderungen durchgeführt.", "success")
    return redirect(url_for("admin.guthaben.guthaben_management"))
