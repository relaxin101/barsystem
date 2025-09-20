from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import or_, func, text
from models import db, Mitglied, Artikel, Buchung
from datetime import datetime

bar_bp = Blueprint('bar', __name__)


@bar_bp.route("/")
def index():
    """Startseite der Bar-Anwendung (hier wird später die Suche/Bedienung stattfinden)."""
    alle_mitglieder = Mitglied.query.order_by(Mitglied.name).all()
    alle_artikel = Artikel.query.order_by(Artikel.name).all()
    return redirect(url_for("bar.bar_interface"))


@bar_bp.route("/api/members", methods=["GET"])
def get_members_api():
    search_term = request.args.get("search", "")  # Suchbegriff aus den URL-Parametern

    if search_term:
        # PostgreSQL text search across name and nickname columns
        # Using to_tsvector for full-text search
        members_query = Mitglied.query.filter(
            text("to_tsvector('german', name || ' ' || nickname) @@ plainto_tsquery('german', :search_term)")
        ).params(search_term=search_term)
    else:
        members_query = Mitglied.query

    members = members_query.order_by(Mitglied.name).all()

    # Mitgliederdaten in ein Listen von Dictionaries umwandeln
    members_data = []
    for member in members:
        members_data.append(
            {
                "id": member.id,
                "name": member.name,
                "nickname": member.nickname,
                "guthaben": member.guthaben,
                # Füge hier alle weiteren Daten hinzu, die du im Frontend benötigst
            }
        )

    return jsonify({"success": True, "members": members_data})


@bar_bp.route("/bar", methods=["GET", "POST"])
def bar_interface():
    """
    Hauptinterface für die Bar.
    Zeigt eine Mitglieder-Suchleiste und nach der Auswahl die Artikel an.
    """
    # Mitglieder abrufen
    all_mitglieder_objects = Mitglied.query.order_by(
        Mitglied.name
    ).all()  # Hier holen wir die ORM-Objekte

    # Mitgliederobjekte in eine Liste von Dictionaries umwandeln
    mitglieder_data = []
    for mitglied in all_mitglieder_objects:
        mitglieder_data.append(
            {"id": mitglied.id, "name": mitglied.name, "nickname": mitglied.nickname, "guthaben": mitglied.guthaben}
        )

    artikel_liste = Artikel.query.order_by(Artikel.name).all()

    return render_template(
        "bar/bar_interface.html",
        mitglieder=mitglieder_data,  # Jetzt übergeben wir die Liste der Dictionaries
        artikel=artikel_liste,
    )


@bar_bp.route("/bar/buchen", methods=["POST"])
def buchen():
    data = request.get_json()  # Daten als JSON empfangen

    mitglied_id = data.get("mitglied_id")
    artikel_id = data.get("artikel_id")
    menge = data.get("menge")

    if not all([mitglied_id, artikel_id, menge]):
        return jsonify({"success": False, "message": "Fehlende Daten."}), 400

    mitglied = Mitglied.query.get(mitglied_id)
    artikel = Artikel.query.get(artikel_id)

    if not mitglied or not artikel:
        return (
            jsonify(
                {"success": False, "message": "Mitglied oder Artikel nicht gefunden."}
            ),
            404,
        )

    try:
        menge = int(menge)  # Stelle sicher, dass Menge eine ganze Zahl ist
        if menge <= 0:
            return (
                jsonify({"success": False, "message": "Menge muss positiv sein."}),
                400,
            )

        # NEU: Bestand prüfen, bevor der Verkauf stattfindet
        if artikel.bestand < menge:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f"Nicht genügend {artikel.name} auf Lager. Verfügbar: {artikel.bestand}",
                    }
                ),
                400,
            )

        gesamtpreis = artikel.preis * menge

        if mitglied.guthaben < gesamtpreis:
            return (
                jsonify({"success": False, "message": "Nicht genügend Guthaben."}),
                400,
            )

        # 1. Guthaben des Mitglieds aktualisieren
        mitglied.guthaben -= gesamtpreis

        # 2. BESTAND DES ARTIKELS REDUZIEREN - DIESE ZEILE HAT GEFEHLT!
        artikel.bestand -= menge  # <-- HIER HINZUGEFÜGT!

        # 3. Buchung in der Datenbank speichern
        neue_buchung = Buchung(
            mitglied_id=mitglied.id,
            artikel_id=artikel.id,
            menge=menge,
            preis_pro_einheit=artikel.preis,  # Speichern wir den Preis zum Zeitpunkt des Kaufs
            gesamtpreis=gesamtpreis,
            zeitstempel=datetime.utcnow(),  # Aktuellen UTC-Zeitstempel verwenden
            storniert=False,  # Standardmäßig nicht storniert
        )
        db.session.add(neue_buchung)

        # 4. Alle Änderungen (Guthaben, Bestand und neue Buchung) in der Datenbank speichern
        db.session.commit()

        # Erfolgreiche JSON-Antwort an das Frontend
        return jsonify(
            {
                "success": True,
                "message": "Buchung erfolgreich!",
                "new_balance": mitglied.guthaben,
                "artikel_name": artikel.name,  # Optional: nützlich für Bestätigungstexte im Frontend
                "menge": menge,
                "gesamtpreis": gesamtpreis,
                "new_artikel_bestand": artikel.bestand,  # Optional: Neuen Bestand zurückgeben
            }
        )

    except ValueError:
        return (
            jsonify({"success": False, "message": "Ungültige Menge oder Daten."}),
            400,
        )
    except Exception as e:
        db.session.rollback()  # Wichtig: Rollback bei Fehlern
        print(f"Fehler bei der Buchung: {e}")  # Fehler im Terminal loggen
        return (
            jsonify(
                {"success": False, "message": "Interner Serverfehler bei der Buchung."}
            ),
            500,
        )
