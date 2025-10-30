from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Mitglied(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text(), unique=False, nullable=False)
    nickname = db.Column(db.Text(), nullable=True)
    email = db.Column(db.Text(), nullable=True, unique=True)
    guthaben = db.Column(db.Float, default=0.0)
    blacklist = db.Column(db.Boolean, default=False)

    buchungen_von_mitglied = db.relationship(
        "Buchung", back_populates="mitglied_obj", lazy=True
    )

    def __repr__(self):
        return f"<Mitglied {self.name} (Guthaben: {self.guthaben:.2f}€)>"


class Artikel(db.Model):
    """
    Modell für einen Artikel (Getränk, Snack, etc.).
    Speichert Name und Preis.
    """

    id = db.Column(db.Integer, primary_key=True)
    order = db.Column(db.Integer, nullable=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    preis = db.Column(db.Float, nullable=False)
    bestand = db.Column(db.Integer, nullable=False, default=0)
    mindestbestand = db.Column(db.Integer, default=5, nullable=False)  # Standardwert 5
    buchungen = db.relationship(
        "Buchung", lazy=True
    )  # Stelle sicher, dass diese auch hier ist

    buchungen_von_artikel = db.relationship(
        "Buchung", back_populates="artikel_obj", lazy=True
    )

    def __repr__(self):
        return f"<Artikel {self.name} ({self.preis:.2f}€) - Bestand: {self.bestand}>"


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.Text(), unique=True, nullable=False)
    password = db.Column(db.Text(), nullable=False)  # Speichert das gehashte Passwort
    is_admin = db.Column(
        db.Boolean, default=False
    )  # Optional: Feld, um Admins zu kennzeichnen

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def __repr__(self):
        return f"<User {self.username}>"

    # Methoden, die Flask-Login für die Benutzerverwaltung benötigt:
    def get_id(self):
        # Gibt die eindeutige ID des Benutzers zurück
        return str(self.id)

    def is_active(self):
        # Gibt True zurück, wenn der Benutzer aktiv ist (nicht deaktiviert)
        return True

    def is_authenticated(self):
        # Gibt True zurück, wenn der Benutzer authentifiziert ist (validierte Anmeldeinformationen)
        return True

    def is_anonymous(self):
        # Gibt True zurück, wenn der Benutzer ein anonymer Benutzer ist
        return False


class Buchung(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mitglied_id = db.Column(db.Integer, db.ForeignKey("mitglied.id"), nullable=False)
    artikel_id = db.Column(db.Integer, db.ForeignKey("artikel.id"), nullable=True)
    menge = db.Column(db.Integer, nullable=False)
    preis_pro_einheit = db.Column(db.Float, nullable=False)
    gesamtpreis = db.Column(db.Float, nullable=False)
    zeitstempel = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    storniert = db.Column(
        db.DateTime, default=None, nullable=True
    )  # Wichtig für die Statistiken

    # Beziehungen zu anderen Modellen
    mitglied_obj = db.relationship("Mitglied", back_populates="buchungen_von_mitglied")
    artikel_obj = db.relationship("Artikel", back_populates="buchungen_von_artikel")

    def __repr__(self):
        return f"<Buchung {self.id}: {self.menge}x {self.artikel.name} für {self.mitglied.name}>"


class Bericht(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    sql = db.Column(db.Text, nullable=False)
