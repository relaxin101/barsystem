## Barsystem
Dieses Projekt beherbergt eine einfache Python-Flask-Website zum Managen eines Barsystems mit Personenkonten.
Es umfasst:
- Konto-Blacklisting mit Schwärzung von Konten unter einem bestimmten Limit
- Berichterstellung: Mittels SQL können eigene Berichte geschrieben, gespeichert und als Excel exportiert werden. Siehe "Helpful Queries" weiter unten.
- Produkt- & Mitglieds-Import: Excellisten mit entsprechenden Daten können zum Anlegen und Updaten von Produkten und Mitglieds-Konten benutzt werden. **Für Updates ist die Angabe der entsprechenden ID notwendig.**
- Hotlist von Mitgliedern: Auf der Homepage werden die Mitglieds-Konten, die in letzter Zeit viel gebucht haben absteigend sortiert
- Suche: Eine Schnelle Postgres-Volltextsuche hilft beim schnellen Finden durch Namen und optionale Spitznamen


### Installation
Zur Installation benötigst du [Docker](https://docs.docker.com/engine/install/) bzw. [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/)

Nachdem du das geschafft hast, dupliziere das File `.env.example` und speichere es als `.env`. Das File beinhält die Konfiguration der Website. Ändere am besten zunächst den Wert `SECRET_KEY` auf einen zufälligen string (du brauchst ihn nachher nicht, das soll nur ein Geheimschlüssel sein den die App für diverse Hintergrunddinge benutzt). Mit `ADMIN_USERNAME`, `ADMIN_PASSWORD` konfigurierst du die Login-Daten für das Admin Panel, mit `MINDEST_GUTHABEN` setzt du das Limit, wie weit Personenkonten ins Minus gehen dürfen.

Jetzt kannst du die Website starten! Wenn du ein Terminal in dem Folder öffnest und `docker compose up -d` (+ ENTER) eintippst, beginnt docker mit der Installation der nötigen Komponenten und startet die Website automatisch. (Je nach Internet und Rechenleistung dauert das 5-15 min) Nun kannst du in dem lokalen Netzwerk unter der IP-Adresse des Computers mit dem Port 5000 die Website abrufen. Auf dem Computer wo das Ganze läuft, funktioniert auch [localhost:5000](http://localhost:5000).

#### Optional
Unter static/css/style.css können die Hauptfarben der Website angepasst werden, siehe

```css
:root {
    --primary-light: #8DB8FF; /* Hintergrundfarbe */
    --primary-main: #FF864D;   /* Akzentfarbe Rot */
    --primary-secondary: #8DB8FF;  /* Akzentfarbe Gold */
    --text-dark: #303030;        /* Dunkler Text für gute Lesbarkeit */
    --text-light: #e8e9eb;    /* Heller Text auf dunklem Hintergrund */
}
```

### ToDo
#### Quality of Life
- [x] Remove parts of an order
- [ ] Checkin alembic migrations
- [ ] Hide products
- [ ] Logo



#### Features
- [ ] Getränkespende
- [ ] Emails
- [ ] Bestand-Tracking




### Helpful Queries
Für die Bericht-Verwaltung sind hier mal ein paar Queries, die prbly häufiger gebraucht werden.
Falls du einen weiteren Bericht brauchst und keine Ahnung von SQL hast, ist darunter noch ein Prompt um eine KI deiner Wahl zu befragen

#### Buchungen letzer Woche
```sql
SELECT mitglied_id, mitglied.name as Name, 
artikel_id, artikel.name as Artikel, menge, preis_pro_einheit, gesamtpreis, 
to_char(zeitstempel, 'DD.MM.YYY') as datum, to_char(zeitstempel, 'HH24:MI') as uhrzeit
FROM buchung
JOIN mitglied ON mitglied.id = mitglied_id
LEFT OUTER JOIN artikel ON artikel.id = artikel_id
WHERE storniert IS NULL
AND zeitstempel >= (NOW() - INTERVAL '1 WEEK')
ORDER BY DATUM DESC, UHRZEIT DESC
```

#### Kürzlich storniert
```sql
SELECT mitglied_id, mitglied.name as Name, 
artikel_id, artikel.name as Artikel, menge, preis_pro_einheit, gesamtpreis, 
to_char(zeitstempel, 'DD.MM.YYY') as datum_buchung, to_char(zeitstempel, 'HH24:MI') as uhrzeit_buchung,
to_char(storniert, 'DD.MM.YYY') as datum_storno, to_char(zeitstempel, 'HH24:MI') as uhrzeit_storno
FROM buchung
JOIN mitglied ON mitglied.id = mitglied_id
LEFT OUTER JOIN artikel ON artikel.id = artikel_id
WHERE storniert IS NOT NULL
ORDER BY datum_buchung DESC, uhrzeit_buchung DESC
LIMIT 20
```

#### Wochenüberblick pro Konto
```sql
SELECT mitglied.id, mitglied.name, mitglied.nickname, COALESCE(SUM(gesamtpreis), 0) as summe
FROM mitglied 
LEFT OUTER JOIN (
    SELECT * from buchung WHERE storniert IS NOT NULL
    AND zeitstempel >= (NOW() - INTERVAL '1 WEEK')
) buchung ON mitglied.id = buchung.mitglied_id

GROUP BY mitglied.id, mitglied.name, mitglied.nickname
ORDER BY mitglied.id
```

 
#### KI Prompt (keine SQL query, nicht in Bericht-Verwaltung kopieren!)
```
Ich habe ein Python-Flask-Projekt für ein Barsystem mit folgenden Database-Models:
class Mitglied(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text(), unique=True, nullable=False)
    nickname = db.Column(db.String(10), nullable=True)
    email = db.Column(db.Text(), nullable=True)
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

Bitte schreibe mir eine SQL query die mir folgendes zurückgibt:
'''
