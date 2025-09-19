from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import or_
from models import (
    db,
    Mitglied,
    Artikel,
    User,
    Buchung,
)  # Importiere deine Datenbankmodelle
import config  # Importiere deine Konfigurationsdatei
import os  # Wird für os.path.exists benötigt
from flask_migrate import Migrate
from sqlalchemy import func
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from datetime import datetime
from flask import redirect, url_for

app = Flask(__name__)

# Lade die Konfiguration aus config.py
app.config.from_object(config)

migrate = Migrate(app, db)

# Initialisiere die Datenbank mit der Flask-App
db.init_app(app)

# Initialisiere Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = (
    "login"  # Wo der Benutzer hingeleitet wird, wenn er nicht angemeldet ist
)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --- Routen der Anwendung ---


@app.route("/")
def index():
    """Startseite der Bar-Anwendung (hier wird später die Suche/Bedienung stattfinden)."""
    alle_mitglieder = Mitglied.query.order_by(Mitglied.name).all()
    alle_artikel = Artikel.query.order_by(Artikel.name).all()
    return redirect(url_for("bar_interface"))


# NEU: Schwellenwert für niedrigen Bestand definieren
BESTAND_WARN_SCHWELLENWERT = 5  # Du kannst diesen Wert anpassen, wie du möchtest


@app.route("/admin")
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
        "admin.html",
        alle_mitglieder=alle_mitglieder_objekte,
        alle_artikel=alle_artikel,  # Das ist die Liste aller Artikel
        artikel_mit_niedrigem_bestand=artikel_mit_niedrigem_bestand,  # Die Liste der kritischen Artikel
        gesamt_einkommen=gesamt_einkommen,  # Nicht vergessen, falls du es im Admin-Bereich anzeigst
        alle_mitglieder_for_recharge=mitglieder_for_template,
        warnungen=warnungen,
        # Hier könntest du auch "buchungen" übergeben, falls du sie anzeigst
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    # Wenn der Benutzer bereits eingeloggt ist, leite ihn zum Admin-Bereich um
    if current_user.is_authenticated:
        flash("Du bist bereits eingeloggt!", "info")
        return redirect(
            url_for("admin_bereich")
        )  # Oder welche Seite Admins nach dem Login sehen sollen

    # Verarbeite die Anmeldedaten, wenn das Formular abgesendet wurde (POST-Anfrage)
    if request.method == "POST":
        username = request.form.get(
            "username"
        )  # 'username' ist der Name des Input-Feldes im HTML-Formular
        password = request.form.get(
            "password"
        )  # 'password' ist der Name des Input-Feldes im HTML-Formular

        # Finde den Benutzer in der Datenbank
        user = User.query.filter_by(username=username).first()

        # Überprüfe, ob der Benutzer existiert und das Passwort korrekt ist
        if user and user.check_password(password):
            # Logge den Benutzer ein
            login_user(user)
            flash("Erfolgreich eingeloggt!", "success")

            # Leite den Benutzer auf die Seite um, von der er kam (falls vorhanden)
            next_page = request.args.get("next")
            return redirect(
                next_page or url_for("admin_bereich")
            )  # Oder die Hauptseite, wenn 'next' nicht gesetzt ist
        else:
            # Fehlermeldung bei falschem Benutzernamen/Passwort
            flash(
                "Login fehlgeschlagen. Bitte überprüfe deinen Benutzernamen und dein Passwort.",
                "error",
            )

    # Zeige das Login-Formular an (GET-Anfrage oder bei fehlgeschlagenem POST)
    return render_template("login.html")


@app.route("/logout")
@login_required  # Nur angemeldete Benutzer können sich ausloggen
def logout():
    logout_user()
    flash("Du wurdest abgemeldet.", "info")
    return redirect(url_for("index"))


# --- Admin-Funktionen (Beispiele) ---


@app.route("/admin/add_mitglied", methods=["POST"])
@login_required
def add_mitglied():
    """Ein neues Mitglied hinzufügen."""
    name = request.form.get("name")
    pin = request.form.get("pin")
    if not name or not pin:
        flash("Name und PIN dürfen nicht leer sein!", "error")
        return redirect(url_for("admin_bereich"))

    neues_mitglied = Mitglied(name=name, pin=pin, guthaben=0.0)
    try:
        db.session.add(neues_mitglied)
        db.session.commit()
        flash(f'Mitglied "{name}" erfolgreich hinzugefügt.', "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Hinzufügen des Mitglieds: {e}", "error")
    return redirect(url_for("admin_bereich"))


@app.route("/admin/add_artikel", methods=["POST"])
@login_required
def add_artikel():
    """Einen neuen Artikel hinzufügen."""
    name = request.form.get("name")
    preis = request.form.get("preis")
    if not name or not preis:
        flash("Name und Preis dürfen nicht leer sein!", "error")
        return redirect(url_for("admin_bereich"))

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
    return redirect(url_for("admin_bereich"))


# Dies ist die neue ROUTE, die die HTML-Seite 'aufladen.html' anzeigt.
@app.route("/aufladen", methods=["GET"])  # Der URL-Pfad, auf den der Browser zugreift
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

    return render_template("aufladen.html", mitglieder=mitglieder_for_template)


# Das Frontend sendet an '/mitglied/guthaben_aufladen'.
@app.route("/mitglied/guthaben_aufladen", methods=["POST"])
@login_required  # Behalte dies bei, oder ändere es zu @admin_required, falls nur Admins aufladen dürfen
def guthaben_aufladen():
    """Guthaben eines Mitglieds aufladen (AJAX-Version)."""

    # Daten aus dem JSON-Body der Anfrage abrufen, nicht aus request.form
    data = request.get_json()
    mitglied_id = data.get("mitglied_id")
    betrag = data.get(
        "amount"
    )  # Der Schlüssel im Frontend-JSON ist 'amount', nicht 'betrag'

    # Prüfen, ob Daten vorhanden sind
    if (
        not mitglied_id or betrag is None
    ):  # betrag kann 0 sein, daher nicht 'not betrag'
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Fehlende Daten (Mitglied ID oder Betrag).",
                }
            ),
            400,
        )

    try:
        betrag = float(betrag)
        if betrag <= 0:
            return (
                jsonify({"success": False, "message": "Betrag muss positiv sein."}),
                400,
            )

        mitglied = Mitglied.query.get(mitglied_id)
        if mitglied:
            mitglied.guthaben += betrag
            db.session.commit()
            # Erfolgreiche Antwort als JSON zurückgeben
            return jsonify(
                {
                    "success": True,
                    "message": f"Guthaben von {mitglied.name} um {betrag:.2f}€ aufgeladen.",
                    "guthaben": mitglied.guthaben,  # Neuen Kontostand zurückgeben
                }
            )
        else:
            return (
                jsonify({"success": False, "message": "Mitglied nicht gefunden."}),
                404,
            )

    except ValueError:
        # Fehler bei der Typumwandlung des Betrags
        return (
            jsonify(
                {"success": False, "message": "Betrag muss eine gültige Zahl sein!"}
            ),
            400,
        )
    except Exception as e:
        # Allgemeine Fehlerbehandlung
        db.session.rollback()  # Datenbank-Transaktion rückgängig machen
        print(f"Fehler beim Aufladen: {e}")  # Fehler im Terminal loggen
        return (
            jsonify(
                {"success": False, "message": "Interner Serverfehler beim Aufladen."}
            ),
            500,
        )


@app.route("/admin/buchungshistorie")
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

    return render_template("buchungshistorie.html", buchungen=buchungen_for_template)


@app.route("/top_verkaeufer")
@login_required
def top_verkaeufer():
    # Wir gruppieren nach artikel_id und summieren die Menge
    # Außerdem joinen wir mit Artikel, um den Namen des Artikels zu bekommen
    top_artikel = (
        db.session.query(
            Artikel.name, func.sum(Buchung.menge).label("total_menge_verkauft")
        )
        .join(Buchung)
        .filter(Buchung.storniert == False)
        .group_by(Artikel.name)
        .order_by(func.sum(Buchung.menge).desc())
        .limit(10)
        .all()
    )  # Hier holen wir die Top 10

    # Beispiel für Top-Umsatz-Artikel:
    top_umsatz_artikel = (
        db.session.query(
            Artikel.name, func.sum(Buchung.gesamtpreis).label("total_umsatz")
        )
        .join(Buchung)
        .filter(Buchung.storniert == False)
        .group_by(Artikel.name)
        .order_by(func.sum(Buchung.gesamtpreis).desc())
        .limit(10)
        .all()
    )

    # ... und so weiter für andere Top-Listen, falls vorhanden.

    return render_template(
        "top_verkaeufer.html",
        top_artikel=top_artikel,
        top_umsatz_artikel=top_umsatz_artikel,
    )  # Passe die Rückgabe an deine Variablen an


# --- Hier kommen später Routen für die eigentliche Bar-Bedienung hin ---
# --- Routen für die Bar-Bedienung ---


@app.route("/api/members", methods=["GET"])
def get_members_api():
    search_term = request.args.get("search", "")  # Suchbegriff aus den URL-Parametern

    if search_term:
        members_query = Mitglied.query.filter(
            or_(Mitglied.name.ilike(f"%{search_term}%"), Mitglied.pin == search_term)
        )
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
                "guthaben": member.guthaben,
                # Füge hier alle weiteren Daten hinzu, die du im Frontend benötigst
            }
        )

    return jsonify({"success": True, "members": members_data})


@app.route("/bar", methods=["GET", "POST"])
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
            {"id": mitglied.id, "name": mitglied.name, "guthaben": mitglied.guthaben}
        )

    artikel_liste = Artikel.query.order_by(Artikel.name).all()

    return render_template(
        "bar_interface.html",
        mitglieder=mitglieder_data,  # Jetzt übergeben wir die Liste der Dictionaries
        artikel=artikel_liste,
    )


@app.route("/bar/buchen", methods=["POST"])
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


@app.route("/mindestbestand_setzen/<int:artikel_id>", methods=["POST"])
@login_required  # Oder @admin_required, falls zutreffend
def mindestbestand_setzen(artikel_id):
    if request.method == "POST":
        try:
            # Den neuen Mindestbestand aus dem Formular abrufen
            neuer_mindestbestand = int(request.form.get("neuer_mindestbestand"))

            if neuer_mindestbestand < 0:
                flash("Der Mindestbestand kann nicht negativ sein.", "danger")
                return redirect(url_for("admin_bereich"))

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

    return redirect(url_for("admin_bereich"))  # Zurück zur Admin-Seite


# --- Routen für Mitglieder bearbeiten/löschen ---


@app.route("/admin/mitglied/bearbeiten/<int:mitglied_id>", methods=["GET", "POST"])
@login_required
def mitglied_bearbeiten(mitglied_id):
    mitglied = Mitglied.query.get_or_404(mitglied_id)
    if request.method == "POST":
        try:
            mitglied.name = request.form["name"]
            mitglied.pin = request.form["pin"]
            # Guthaben nur aktualisieren, wenn es explizit im Formularfeld ist
            # und nicht leer, da wir hier primär Name/PIN bearbeiten.
            # Für Guthabenaufladung gibt es die separate Funktion.
            if "guthaben" in request.form and request.form["guthaben"]:
                mitglied.guthaben = float(request.form["guthaben"])

            db.session.commit()
            flash("Mitglied erfolgreich aktualisiert!", "success")
            return redirect(url_for("admin_bereich"))
        except Exception as e:
            db.session.rollback()
            flash(f"Fehler beim Aktualisieren des Mitglieds: {e}", "error")
    return render_template("mitglied_bearbeiten.html", mitglied=mitglied)


@app.route("/admin/mitglied/loeschen/<int:mitglied_id>", methods=["POST"])
@login_required
def mitglied_loeschen(mitglied_id):
    mitglied = Mitglied.query.get_or_404(mitglied_id)
    try:
        # Zuerst alle Transaktionen löschen, die mit diesem Mitglied verknüpft sind
        # (oder Kaskadenlöschung in den Modellen definieren, aber das ist sicherer)
        Transaktion.query.filter_by(mitglied_id=mitglied.id).delete()
        db.session.delete(mitglied)
        db.session.commit()
        flash("Mitglied erfolgreich gelöscht!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Löschen des Mitglieds: {e}", "error")
    return redirect(url_for("admin_bereich"))


# --- Routen für Artikel bearbeiten/löschen ---


@app.route("/admin/artikel/bearbeiten/<int:artikel_id>", methods=["GET", "POST"])
@login_required
def artikel_bearbeiten(artikel_id):
    artikel = Artikel.query.get_or_404(artikel_id)
    if request.method == "POST":
        try:
            artikel.name = request.form["name"]
            artikel.preis = float(request.form["preis"])
            db.session.commit()
            flash("Artikel erfolgreich aktualisiert!", "success")
            return redirect(url_for("admin_bereich"))
        except Exception as e:
            db.session.rollback()
            flash(f"Fehler beim Aktualisieren des Artikels: {e}", "error")
    return render_template("artikel_bearbeiten.html", artikel=artikel)


@app.route("/admin/artikel/loeschen/<int:artikel_id>", methods=["POST"])
@login_required
def artikel_loeschen(artikel_id):
    artikel = Artikel.query.get_or_404(artikel_id)
    try:
        # Zuerst alle Transaktionen löschen, die mit diesem Artikel verknüpft sind
        Transaktion.query.filter_by(artikel_id=artikel.id).delete()
        db.session.delete(artikel)
        db.session.commit()
        flash("Artikel erfolgreich gelöscht!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Löschen des Artikels: {e}", "error")
    return redirect(url_for("admin_bereich"))


@app.route("/bestand_anpassen/<int:artikel_id>", methods=["POST"])
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

    return redirect(url_for("admin_bereich"))  # Zurück zur Admin-Seite


@app.route("/bestand_auf_setzen/<int:artikel_id>", methods=["POST"])
@login_required  # Oder @admin_required
def bestand_auf_setzen(artikel_id):
    if request.method == "POST":
        try:
            # Die neue Bestandsmenge aus dem Formular abrufen
            neuer_bestand = int(request.form.get("neuer_bestand"))

            if neuer_bestand < 0:
                flash("Der Bestand kann nicht negativ sein.", "danger")
                return redirect(url_for("admin_bereich"))

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

    return redirect(url_for("admin_bereich"))  # Zurück zur Admin-Seite


# --- Routen für Berichte und Auswertungen ---


@app.route("/admin/berichte")
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
        "berichte.html",
        gesamt_einnahmen=gesamt_einnahmen,
        verkaeufe_pro_artikel=verkaeufe_pro_artikel,
        guthaben_uebersicht=guthaben_uebersicht,
    )


@app.route("/admin/change_password", methods=["GET", "POST"])
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
            return redirect(url_for("admin_bereich"))  # Zurück zum Admin-Bereich

    return render_template("change_password.html")


@app.template_filter("float_format")
def float_format_filter(value):
    return "{:.2f}".format(value).replace(".", ",")


app.jinja_env.filters["float_format"] = float_format_filter

# Stornierung#


@app.route("/admin/storniere_buchung/<int:buchung_id>", methods=["GET", "POST"])
@login_required
def storniere_buchung(buchung_id):
    """Storniert eine spezifische Buchung und korrigiert das Guthaben des Mitglieds."""

    buchung = Buchung.query.get(buchung_id)

    if not buchung:
        flash("Buchung nicht gefunden.", "error")
        return redirect(url_for("buchungshistorie"))

    if buchung.storniert:
        flash("Diese Buchung wurde bereits storniert.", "info")
        return redirect(url_for("buchungshistorie"))

    try:
        # Guthaben des Mitglieds korrigieren
        mitglied = buchung.mitglied
        if mitglied:
            mitglied.guthaben += buchung.gesamtpreis  # Guthaben zurückerstatten

        # Bestand des Artikels wieder erhöhen (DAHER IST ES + UND NICHT -)
        artikel = buchung.artikel  # <-- Artikel aus der Buchung holen
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

    return redirect(url_for("buchungshistorie"))


# Hier dann weitere Sachen einfügen

# --- App starten ---
if __name__ == "__main__":  # <-- Startet ganz links
    with app.app_context():  # <-- Startet ganz links, auf gleicher Ebene wie 'if __name__'
        # Der gesamte folgende Code MUSS um EINE Ebene eingerückt sein (z.B. 4 Leerzeichen)
        # --- Teil 1: Datenbank überprüfen und erstellen ---
        if not os.path.exists(os.path.join(config.BASE_DIR, "barsystem.db")):
            print("Datenbank 'barsystem.db' wird erstellt...")
            db.create_all()
            print("Datenbank erfolgreich erstellt!")
        else:
            print("Datenbank 'barsystem.db' existiert bereits.")

        # --- Teil 2: Admin-Benutzer überprüfen und erstellen ---
        if not User.query.filter_by(username=config.ADMIN_USERNAME).first():
            print(f"Erstelle initialen Admin-Benutzer: {config.ADMIN_USERNAME}")
            admin_user = User(username=config.ADMIN_USERNAME)
            admin_user.set_password(config.ADMIN_PASSWORD)  # Passwort wird gehasht
            db.session.add(admin_user)
            db.session.commit()
            print("Admin-Benutzer erfolgreich erstellt!")

        # DIESE ZEILE MUSS AUF DER GLEICHEN EBENE WIE 'if not os.path.exists...' und 'if not AdminUser...' SEIN!
        # Sie gehört also ZUM 'with app.app_context():' Block.
        app.run(host="0.0.0.0", debug=True)
