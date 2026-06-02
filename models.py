from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from config import MINDEST_GUTHABEN

db = SQLAlchemy()


class Mitglied(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text(), unique=False, nullable=False)
    nickname = db.Column(db.Text(), nullable=True)
    email = db.Column(db.Text(), nullable=True)
    guthaben = db.Column(db.Integer, default=0)
    blacklist = db.Column(db.Boolean, default=False)
    aktiv = db.Column(db.Boolean, nullable=False, default=True)
    gepinnt = db.Column(db.Boolean, nullable=False, default=False)
    schwaerzungs_grenze = db.Column(db.Integer, nullable=True, default=MINDEST_GUTHABEN)
    buchungen_von_mitglied = db.relationship(
        "Buchung", back_populates="mitglied_obj", lazy=True
    )

    def __repr__(self):
        return f"<Mitglied {self.name} (Guthaben: {self.guthaben / 100:.2f}€)>"


class Artikel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reihenfolge = db.Column(db.Integer, nullable=True)
    aktiv = db.Column(db.Boolean, nullable=False, default=True)
    name = db.Column(db.Text, unique=True, nullable=False)
    preis = db.Column(db.Integer, nullable=False)
    typ = db.Column(db.String(10), nullable=False, default='volumen')
    volumen_liter = db.Column(db.Float, nullable=True, default=0.5)
    reinalkohol_liter = db.Column(db.Float, nullable=True, default=0.0)
    buchungen = db.relationship("Buchung", lazy=True)
    buchungen_von_artikel = db.relationship(
        "Buchung", back_populates="artikel_obj", lazy=True
    )

    def __repr__(self):
        return f"<Artikel {self.name} ({self.preis / 100:.2f}€)>"


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.Text(), unique=True, nullable=False)
    password = db.Column(db.Text(), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def __repr__(self):
        return f"<User {self.username}>"

    def get_id(self):
        return str(self.id)

    def is_active(self):
        return True

    def is_authenticated(self):
        return True

    def is_anonymous(self):
        return False


class Buchung(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mitglied_id = db.Column(db.Integer, db.ForeignKey("mitglied.id"), nullable=False)
    artikel_id = db.Column(db.Integer, db.ForeignKey("artikel.id"), nullable=True)
    abrechnungs_id = db.Column(db.Integer, db.ForeignKey("abrechnung.id"), nullable=True)
    beschreibung = db.Column(db.Text, nullable=True)
    menge = db.Column(db.Integer, nullable=False)
    preis_pro_einheit = db.Column(db.Integer, nullable=False)
    gesamtpreis = db.Column(db.Integer, nullable=False)
    zeitstempel = db.Column(db.DateTime, default=datetime.now, nullable=False)
    storno = db.Column(db.Boolean, nullable=False, default=False)
    storno_updated_at = db.Column(db.DateTime, default=None, nullable=True)

    mitglied_obj = db.relationship("Mitglied", back_populates="buchungen_von_mitglied")
    artikel_obj = db.relationship("Artikel", back_populates="buchungen_von_artikel")
    abrechnung_obj = db.relationship("Abrechnung", back_populates="buchungen")

    def __repr__(self):
        artikel_name = self.artikel_obj.name if self.artikel_obj is not None else None
        return f"<Buchung {self.id} - {self.beschreibung}: {self.menge}x {artikel_name} für {self.mitglied_obj.name}>"


class Abrechnung(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    zeitstempel = db.Column(db.DateTime, default=datetime.now, nullable=False)
    buchungen = db.relationship("Buchung", back_populates="abrechnung_obj", lazy=True)

    def __repr__(self):
        return f"<Abrechnung {self.id} {self.name}>"


class RankingArtikel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    artikel_id = db.Column(db.Integer, db.ForeignKey("artikel.id"), unique=True, nullable=False)
    artikel_obj = db.relationship("Artikel")


class RankingKonfiguration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stunden = db.Column(db.Integer, nullable=False, default=24)


class Bericht(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    sql = db.Column(db.Text, nullable=False)


class Aussendung(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.Text, nullable=False)
    message = db.Column(db.Text, nullable=False)
    frequenz = db.Column(db.String(50), nullable=False, default="7")
    member_days = db.Column(db.Integer, nullable=False, default=7)
    alle_mitglieder = db.Column(db.Boolean, nullable=False, default=False)
    brevo_template = db.Column(db.Integer, nullable=True)
    aktiv = db.Column(db.Boolean, default=True)
    last_run = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<Aussendung {self.subject} ({self.frequenz})>"
