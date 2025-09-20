from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import func
from models import db, Mitglied, Artikel, User, Buchung
from flask_login import login_required, current_user
from datetime import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# NEU: Schwellenwert für niedrigen Bestand definieren
BESTAND_WARN_SCHWELLENWERT = 5  # Du kannst diesen Wert anpassen, wie du möchtest


@admin_bp.route("/")
@login_required  # Nur für angemeldete Benutzer (Admins) zugänglich
def admin_bereich():
    """Admin-Bereich"""

    # --- Bereich für Gesamt-Einkommen (falls vorhanden) ---
    gesamt_einkommen_result = (
        db.session.query(func.sum(Buchung.gesamtpreis))
        .filter(Buchung.storniert == False)
        .scalar()
    )
    gesamt_einkommen = (
        gesamt_einkommen_result if gesamt_einkommen_result is not None else 0.0
    )

    # --- Bereich für Mitglieder ---
    alle_mitglieder_objekte = Mitglied.query.order_by(Mitglied.name).all()
    mitglieder_for_template = []
    for mitglied_obj in alle_mitglieder_objekte:
        mitglieder_for_template.append(
            {
                "id": mitglied_obj.id,
                "name": mitglied_obj.name,
                "guthaben": mitglied_obj.guthaben,
                # Füge hier weitere Attribute hinzu, die du im Admin-Bereich im JS nutzen möchtest
            }
        )

    # --- Bereich für Artikel ---
    alle_artikel = Artikel.query.order_by(Artikel.name).all()

    warnungen = []

    # NEU: Artikel mit niedrigem Bestand identifizieren
    artikel_mit_niedrigem_bestand = []
    for artikel_item in alle_artikel:  # Hier iterieren wir über alle_artikel
        if artikel_item.bestand < artikel_item.mindestbestand:
            warnungen.append(
                f'Achtung: Der Bestand von "{artikel_item.name}" ist mit {artikel_item.bestand} Stück unter dem individuellen Mindestbestand von {artikel_item.mindestbestand}!'
            )

    # --- Bereich für Buchungshistorie (falls vorhanden, hier nur Platzhalter) ---
    # buchungen = Buchung.query.order_by(Buchung.zeitstempel.desc()).limit(20).all()

    # --- Daten an das Template übergeben ---
    return render_template(
        "admin/admin.html",
        alle_mitglieder=alle_mitglieder_objekte,
        alle_artikel=alle_artikel,  # Das ist die Liste aller Artikel
        artikel_mit_niedrigem_bestand=artikel_mit_niedrigem_bestand,  # Die Liste der kritischen Artikel
        gesamt_einkommen=gesamt_einkommen,  # Nicht vergessen, falls du es im Admin-Bereich anzeigst
        alle_mitglieder_for_recharge=mitglieder_for_template,
        warnungen=warnungen,
        # Hier könntest du auch "buchungen" übergeben, falls du sie anzeigst
    )


@admin_bp.route("/add_mitglied", methods=["POST"])
@login_required
def add_mitglied():
    """Ein neues Mitglied hinzufügen."""
    name = request.form.get("name")
    nickname = request.form.get("nickname")
    if not name or not nickname:
        flash("Name und Nickname dürfen nicht leer sein!", "error")
        return redirect(url_for("admin.admin_bereich"))

    neues_mitglied = Mitglied(name=name, nickname=nickname, guthaben=0.0)
    try:
        db.session.add(neues_mitglied)
        db.session.commit()
        flash(f'Mitglied "{name}" erfolgreich hinzugefügt.', "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Hinzufügen des Mitglieds: {e}", "error")
    return redirect(url_for("admin.admin_bereich"))


@admin_bp.route("/add_artikel", methods=["POST"])
@login_required
def add_artikel():
    """Einen neuen Artikel hinzufügen."""
    name = request.form.get("name")
    preis = request.form.get("preis")
    if not name or not preis:
        flash("Name und Preis dürfen nicht leer sein!", "error")
        return redirect(url_for("admin.admin_bereich"))

    try:
        preis = float(preis)
        neuer_artikel = Artikel(name=name, preis=preis)
        db.session.add(neuer_artikel)
        db.session.commit()
        flash(f'Artikel "{name}" erfolgreich hinzugefügt.', "success")
    except ValueError:
        flash("Preis muss eine gültige Zahl sein!", "error")
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Hinzufügen des Artikels: {e}", "error")
    return redirect(url_for("admin.admin_bereich"))


@admin_bp.route("/buchungshistorie")
@login_required  # Nur für angemeldete Benutzer (Admins) zugänglich
def buchungshistorie():
    """Zeigt alle Buchungen an."""

    # Alle Buchungen abrufen, die neuesten zuerst
    alle_buchungen_objekte = Buchung.query.order_by(Buchung.zeitstempel.desc()).all()

    # Umwandlung der Buchungsobjekte in Dictionaries für das Template
    buchungen_for_template = []
    for buchung_obj in alle_buchungen_objekte:
        # Sicherstellen, dass Mitglied und Artikel geladen sind, bevor auf ihre Attribute zugegriffen wird
        mitglied_name = (
            buchung_obj.mitglied_obj.name
            if buchung_obj.mitglied_obj
            else "Unbekanntes Mitglied"
        )
        artikel_name = (
            buchung_obj.artikel_obj.name
            if buchung_obj.artikel_obj
            else "Unbekannter Artikel"
        )
        buchungen_for_template.append(
            {
                "id": buchung_obj.id,
                "mitglied_name": mitglied_name,
                "artikel_name": artikel_name,
                "menge": buchung_obj.menge,
                "preis_pro_einheit": buchung_obj.preis_pro_einheit,
                "gesamtpreis": buchung_obj.gesamtpreis,
                "zeitstempel": buchung_obj.zeitstempel.strftime(
                    "%d.%m.%Y %H:%M:%S"
                ),  # Formatierung für bessere Lesbarkeit
                "storniert": buchung_obj.storniert,
            }
        )

    return render_template("admin/buchungshistorie.html", buchungen=buchungen_for_template)


@admin_bp.route("/mitglied/bearbeiten/<int:mitglied_id>", methods=["GET", "POST"])
@login_required
def mitglied_bearbeiten(mitglied_id):
    mitglied = Mitglied.query.get_or_404(mitglied_id)
    if request.method == "POST":
        try:
            mitglied.name = request.form["name"]
            mitglied.nickname = request.form["nickname"]
            # Guthaben nur aktualisieren, wenn es explizit im Formularfeld ist
            # und nicht leer, da wir hier primär Name/PIN bearbeiten.
            # Für Guthabenaufladung gibt es die separate Funktion.
            if "guthaben" in request.form and request.form["guthaben"]:
                mitglied.guthaben = float(request.form["guthaben"])

            db.session.commit()
            flash("Mitglied erfolgreich aktualisiert!", "success")
            return redirect(url_for("admin.admin_bereich"))
        except Exception as e:
            db.session.rollback()
            flash(f"Fehler beim Aktualisieren des Mitglieds: {e}", "error")
    return render_template("admin/mitglied_bearbeiten.html", mitglied=mitglied)


@admin_bp.route("/mitglied/loeschen/<int:mitglied_id>", methods=["POST"])
@login_required
def mitglied_loeschen(mitglied_id):
    mitglied = Mitglied.query.get_or_404(mitglied_id)
    try:
        # Zuerst alle Transaktionen löschen, die mit diesem Mitglied verknüpft sind
        # (oder Kaskadenlöschung in den Modellen definieren, aber das ist sicherer)
        Buchung.query.filter_by(mitglied_id=mitglied.id).delete()
        db.session.delete(mitglied)
        db.session.commit()
        flash("Mitglied erfolgreich gelöscht!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Löschen des Mitglieds: {e}", "error")
    return redirect(url_for("admin.admin_bereich"))


@admin_bp.route("/artikel/bearbeiten/<int:artikel_id>", methods=["GET", "POST"])
@login_required
def artikel_bearbeiten(artikel_id):
    artikel = Artikel.query.get_or_404(artikel_id)
    if request.method == "POST":
        try:
            artikel.name = request.form["name"]
            artikel.preis = float(request.form["preis"])
            db.session.commit()
            flash("Artikel erfolgreich aktualisiert!", "success")
            return redirect(url_for("admin.admin_bereich"))
        except Exception as e:
            db.session.rollback()
            flash(f"Fehler beim Aktualisieren des Artikels: {e}", "error")
    return render_template("admin/artikel_bearbeiten.html", artikel=artikel)


@admin_bp.route("/artikel/loeschen/<int:artikel_id>", methods=["POST"])
@login_required
def artikel_loeschen(artikel_id):
    artikel = Artikel.query.get_or_404(artikel_id)
    try:
        # Zuerst alle Transaktionen löschen, die mit diesem Artikel verknüpft sind
        Buchung.query.filter_by(artikel_id=artikel.id).delete()
        db.session.delete(artikel)
        db.session.commit()
        flash("Artikel erfolgreich gelöscht!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Löschen des Artikels: {e}", "error")
    return redirect(url_for("admin.admin_bereich"))


@admin_bp.route("/berichte")
@login_required
def berichte():
    # Gesamteinnahmen
    gesamt_einnahmen_result = (
        db.session.query(func.sum(Buchung.gesamtpreis))
        .filter(Buchung.storniert == False)
        .scalar()
    )
    gesamt_einnahmen = (
        gesamt_einnahmen_result if gesamt_einnahmen_result is not None else 0.0
    )

    # Verkäufe pro Artikel
    verkaeufe_pro_artikel = (
        db.session.query(
            Artikel.name, db.func.sum(Buchung.menge), db.func.sum(Buchung.gesamtpreis)
        )
        .join(Buchung)
        .filter(Buchung.storniert == False)
        .filter(Buchung.storniert == False)
        .group_by(Artikel.name)
        .order_by(db.func.sum(Buchung.gesamtpreis).desc())
        .all()
    )

    # Guthabenübersicht der Mitglieder
    guthaben_uebersicht = Mitglied.query.order_by(Mitglied.name).all()

    return render_template(
        "admin/berichte.html",
        gesamt_einnahmen=gesamt_einnahmen,
        verkaeufe_pro_artikel=verkaeufe_pro_artikel,
        guthaben_uebersicht=guthaben_uebersicht,
    )


@admin_bp.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        old_password = request.form["old_password"]
        new_password = request.form["new_password"]
        confirm_new_password = request.form["confirm_new_password"]

        user = current_user  # Der aktuell eingeloggte Admin-Benutzer

        if not user.check_password(old_password):
            flash("Altes Passwort ist falsch.", "error")
        elif new_password != confirm_new_password:
            flash("Neues Passwort und Bestätigung stimmen nicht überein.", "error")
        else:
            user.set_password(new_password)
            db.session.commit()
            flash("Passwort erfolgreich geändert!", "success")
            return redirect(url_for("admin.admin_bereich"))  # Zurück zum Admin-Bereich

    return render_template("admin/change_password.html")


@admin_bp.route("/storniere_buchung/<int:buchung_id>", methods=["GET", "POST"])
@login_required
def storniere_buchung(buchung_id):
    """Storniert eine spezifische Buchung und korrigiert das Guthaben des Mitglieds."""

    buchung = Buchung.query.get(buchung_id)

    if not buchung:
        flash("Buchung nicht gefunden.", "error")
        return redirect(url_for("admin.buchungshistorie"))

    if buchung.storniert:
        flash("Diese Buchung wurde bereits storniert.", "info")
        return redirect(url_for("admin.buchungshistorie"))

    try:
        # Guthaben des Mitglieds korrigieren
        mitglied = buchung.mitglied_obj
        if mitglied:
            mitglied.guthaben += buchung.gesamtpreis  # Guthaben zurückerstatten

        # Bestand des Artikels wieder erhöhen (DAHER IST ES + UND NICHT -)
        artikel = buchung.artikel_obj  # <-- Artikel aus der Buchung holen
        menge = buchung.menge  # <-- Menge aus der Buchung holen
        if artikel:
            artikel.bestand += menge  # <-- Hier wird der Bestand korrekt erhöht!

        # Buchung als storniert markieren
        buchung.storniert = True

        db.session.commit()
        flash(
            f"Buchung {buchung.id} erfolgreich storniert. {mitglied.name} hat {buchung.gesamtpreis:.2f}€ zurückerhalten.",
            "success",
        )

    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Stornieren der Buchung {buchung_id}: {e}")
        flash(f"Ein Fehler ist beim Stornieren aufgetreten: {e}", "error")

    return redirect(url_for("admin.buchungshistorie"))


# Additional admin routes that were in the original app.py

@admin_bp.route("/aufladen", methods=["GET"])  # Der URL-Pfad, auf den der Browser zugreift
@login_required
def aufladen_seite_anzeigen():  # <-- Dies ist der ENDPUNKT-NAME, den url_for braucht!
    """Rendert die Seite zum Aufladen des Guthabens und übergibt die Mitgliederdaten."""

    # Mitgliederdaten für die Anzeige auf der Seite abrufen und in ein JSON-freundliches Format umwandeln
    alle_mitglieder_objekte = Mitglied.query.order_by(Mitglied.name).all()
    mitglieder_for_template = []
    for mitglied_obj in alle_mitglieder_objekte:
        mitglieder_for_template.append(
            {
                "id": mitglied_obj.id,
                "name": mitglied_obj.name,
                "guthaben": mitglied_obj.guthaben,
            }
        )

    return render_template("admin/aufladen.html", mitglieder=mitglieder_for_template)


# Das Frontend sendet an '/mitglied/guthaben_aufladen'.
@admin_bp.route("/mitglied/guthaben_aufladen", methods=["POST"])
@login_required  # Behalte dies bei, oder ändere es zu @admin_required, falls nur Admins aufladen dürfen
def guthaben_aufladen():
    """Lädt das Guthaben eines Mitglieds auf."""

    data = request.get_json()  # Daten als JSON empfangen

    mitglied_id = data.get("mitglied_id")
    betrag = data.get("betrag")

    if not mitglied_id or not betrag:
        return jsonify({"success": False, "message": "Fehlende Daten."}), 400

    try:
        betrag = float(betrag)  # Stelle sicher, dass Betrag eine Zahl ist
        if betrag <= 0:
            return (
                jsonify({"success": False, "message": "Betrag muss positiv sein."}),
                400,
            )

        mitglied = Mitglied.query.get(mitglied_id)
        if not mitglied:
            return (
                jsonify({"success": False, "message": "Mitglied nicht gefunden."}),
                404,
            )

        # Guthaben des Mitglieds erhöhen
        mitglied.guthaben += betrag

        # Änderungen in der Datenbank speichern
        db.session.commit()

        # Erfolgreiche JSON-Antwort an das Frontend
        return jsonify(
            {
                "success": True,
                "message": f"Guthaben erfolgreich um {betrag:.2f}€ aufgeladen!",
                "new_balance": mitglied.guthaben,
                "mitglied_name": mitglied.name,
            }
        )

    except ValueError:
        return (
            jsonify({"success": False, "message": "Ungültiger Betrag."}),
            400,
        )
    except Exception as e:
        db.session.rollback()  # Wichtig: Rollback bei Fehlern
        print(f"Fehler beim Aufladen: {e}")  # Fehler im Terminal loggen
        return (
            jsonify(
                {"success": False, "message": "Interner Serverfehler beim Aufladen."}
            ),
            500,
        )


@admin_bp.route("/top_verkaeufer")
@login_required
def top_verkaeufer():
    # Wir gruppieren nach artikel_id und summieren die Menge
    # Außerdem joinen wir mit Artikel, um den Namen des Artikels zu bekommen
    top_verkaeufe = (
        db.session.query(
            Artikel.name,
            db.func.sum(Buchung.menge).label("gesamtmenge"),
            db.func.sum(Buchung.gesamtpreis).label("gesamtumsatz"),
        )
        .join(Buchung, Artikel.id == Buchung.artikel_id)
        .filter(Buchung.storniert == False)  # Nur nicht stornierte Buchungen
        .group_by(Artikel.id, Artikel.name)
        .order_by(db.func.sum(Buchung.menge).desc())
        .limit(10)  # Top 10
        .all()
    )

    return render_template(
        "admin/top_verkaeufer.html",
        top_verkaeufe=top_verkaeufe,
    )  # Passe die Rückgabe an deine Variablen an


@admin_bp.route("/mindestbestand_setzen/<int:artikel_id>", methods=["POST"])
@login_required  # Oder @admin_required, falls zutreffend
def mindestbestand_setzen(artikel_id):
    if request.method == "POST":
        try:
            # Den neuen Mindestbestand aus dem Formular abrufen
            neuer_mindestbestand = int(request.form.get("neuer_mindestbestand"))

            if neuer_mindestbestand < 0:
                flash("Der Mindestbestand kann nicht negativ sein.", "danger")
                return redirect(url_for("admin.admin_bereich"))

            artikel = Artikel.query.get_or_404(artikel_id)  # Artikel finden

            alter_mindestbestand = (
                artikel.mindestbestand
            )  # Speichere den alten Wert für die Nachricht
            artikel.mindestbestand = (
                neuer_mindestbestand  # Mindestbestand auf den exakten Wert setzen
            )

            db.session.commit()  # Änderungen speichern
            flash(
                f'Mindestbestand für "{artikel.name}" von {alter_mindestbestand} auf {neuer_mindestbestand} gesetzt.',
                "success",
            )
        except ValueError:
            flash("Ungültiger Wert eingegeben.", "danger")
        except Exception as e:
            flash(f"Fehler beim Setzen des Mindestbestands: {e}", "danger")
            db.session.rollback()  # Bei Fehler Rollback

    return redirect(url_for("admin.admin_bereich"))  # Zurück zur Admin-Seite


@admin_bp.route("/bestand_anpassen/<int:artikel_id>", methods=["POST"])
@login_required  # Oder @admin_required, falls du eine separate Admin-Rolle hast
def bestand_anpassen(artikel_id):
    if request.method == "POST":
        try:
            menge = int(request.form.get("menge"))  # Menge aus dem Formular abrufen

            artikel = Artikel.query.get_or_404(artikel_id)  # Artikel finden

            # Bestand anpassen (addieren)
            artikel.bestand += menge

            db.session.commit()  # Änderungen speichern
            flash(
                f'Bestand für "{artikel.name}" um {menge} aktualisiert. Neuer Bestand: {artikel.bestand}',
                "success",
            )
        except ValueError:
            flash("Ungültige Menge eingegeben.", "danger")
        except Exception as e:
            flash(f"Fehler beim Anpassen des Bestands: {e}", "danger")
            db.session.rollback()  # Bei Fehler Rollback

    return redirect(url_for("admin.admin_bereich"))  # Zurück zur Admin-Seite


@admin_bp.route("/bestand_auf_setzen/<int:artikel_id>", methods=["POST"])
@login_required  # Oder @admin_required
def bestand_auf_setzen(artikel_id):
    if request.method == "POST":
        try:
            # Die neue Bestandsmenge aus dem Formular abrufen
            neuer_bestand = int(request.form.get("neuer_bestand"))

            if neuer_bestand < 0:
                flash("Der Bestand kann nicht negativ sein.", "danger")
                return redirect(url_for("admin.admin_bereich"))

            artikel = Artikel.query.get_or_404(artikel_id)  # Artikel finden

            alter_bestand = (
                artikel.bestand
            )  # Speichere den alten Wert für die Nachricht
            artikel.bestand = neuer_bestand  # Bestand auf den exakten Wert setzen

            db.session.commit()  # Änderungen speichern
            flash(
                f'Bestand für "{artikel.name}" von {alter_bestand} auf {neuer_bestand} gesetzt.',
                "success",
            )
        except ValueError:
            flash("Ungültiger Wert eingegeben.", "danger")
        except Exception as e:
            flash(f"Fehler beim Setzen des Bestands: {e}", "danger")
            db.session.rollback()  # Bei Fehler Rollback

    return redirect(url_for("admin.admin_bereich"))  # Zurück zur Admin-Seite