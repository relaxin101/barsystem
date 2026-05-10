# Barsystem
Dieses Projekt beherbergt eine einfache Python-Flask-Website zum Managen eines Barsystems mit Personenkonten.
Es umfasst:
- Konto-Blacklisting mit Schwärzung von Konten unter einem bestimmten Limit
- Berichterstellung: Mittels SQL können eigene Berichte geschrieben, gespeichert und als Excel exportiert werden. Siehe "Helpful Queries" weiter unten.
- Produkt- & Mitglieds-Import: Excellisten mit entsprechenden Daten können zum Anlegen und Updaten von Produkten und Mitglieds-Konten benutzt werden. **Für Updates ist die Angabe der entsprechenden ID notwendig.**
- Hotlist von Mitgliedern: Auf der Homepage werden die Mitglieds-Konten, die in letzter Zeit viel gebucht haben absteigend sortiert
- Suche: Eine Schnelle Postgres-Volltextsuche hilft beim schnellen Finden durch Namen und optionale Spitznamen


## Installation
Zur Installation benötigst du [Docker](https://docs.docker.com/engine/install/) bzw. [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/)

Nachdem du das geschafft hast, dupliziere das File `.env.example` und speichere es als `.env`. Das File beinhält die Konfiguration der Website. Ändere am besten zunächst den Wert `SECRET_KEY` auf einen zufälligen string (du brauchst ihn nachher nicht, das soll nur ein Geheimschlüssel sein den die App für diverse Hintergrunddinge benutzt). Mit `ADMIN_USERNAME`, `ADMIN_PASSWORD` konfigurierst du die Login-Daten für das Admin Panel, mit `MINDEST_GUTHABEN` setzt du das Limit, wie weit Personenkonten ins Minus gehen dürfen. _admin daten können nachträglich nicht einfach geändert werden, da sie in die datenbank geschrieben werden._

Jetzt kannst du die Website starten! Wenn du ein Terminal in dem Folder öffnest und `docker compose up -d` (+ ENTER) eintippst, beginnt docker mit der Installation der nötigen Komponenten und startet die Website automatisch. (Je nach Internet und Rechenleistung dauert das 5-15 min) Nun kannst du in dem lokalen Netzwerk unter der IP-Adresse des Computers die Website abrufen. Auf dem Computer wo das Ganze läuft, funktioniert auch [localhost](http://localhost). 

Ich empfehle beim Router eine statische IP mittels DHCP zu setzen - in einigen Routern kann man auch Namen vergeben sodass man dann im ganzen Netz unter __http://name-des-geraets__ die Barliste findet.

### Updates
Um Updates zu bekommen musst du das repo mit [git](https://git-scm.com/) gecloned haben und nicht einfach nur runtergeladen haben. 
Dann empfiehlt es sich (semi-)regelmäßig in einem terminal den folgenden befehl auszuführen:

```bash

docker compose down # Stoppe die App
git fetch # Checke nach updates
git stash # Um die customizations etc. zu speichern und für git zu clearen
git reset --hard origin/master # Wendet die updates an
docker compose up -d # Startet die App neu und führt ggf. Datenbank-Migrationen durch
git stash pop # Um die customizations wiederherzustellen
```

**Caveat:** Auch wenn ich versuche alle Datenbank-Migrationen sauber durchzuführen empfiehlt es sich vor jedem Update zumindest die Mitglieder samt Guthabenstände und die Artikel zu sichern (in der Bericht Verwaltung). 
Um das System gänzlich neu aufzusetzen, starte mit `docker compose down -v` - das stoppt die App und löscht auch die gesamte Datenbank - führe dann die restlichen Schritte durch und zum Schluss kannst du dann entsprechende Daten in den jeweiligen Admin-Panels importieren.



### Optionale Customization
Unter `static/css/style.css` können die Hauptfarben der Website angepasst werden, siehe

```css
:root {
    --primary-light: #8DB8FF; /* Hintergrundfarbe */
    --primary-main: #FF864D;   /* Hauptfarbe */
    --primary-secondary: #E2FFE6;  /* Sekundäre Farbe */
}
```

Falls `static/img/logo.png` existiert, wird es im Header neben der Überschrift der Barliste angezeigt.

## Geplante Features
- [x] Email Aussendungen
- [x] Abrechnungen über einen bestimmten Zeitraum
- [ ] Runden schmeißen
- [ ] Email Postfach prüfen für Bankeinzahlungen


## Nützliche Berichte
Für die Bericht-Verwaltung sind hier mal ein paar Queries, die prbly häufiger gebraucht werden.
Falls du einen weiteren Bericht brauchst und keine Ahnung von SQL hast, ist darunter noch ein Prompt um eine KI deiner Wahl zu befragen

### Guthabenformular
Generiert eine Excel die du direkt benutzen kannst um Guthaben einzutragen und aufzubuchen.

```sql
SELECT id, name, nickname, '' as betrag
FROM mitglied
ORDER BY name, nickname
```

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
Zeigt die letzten 20 stornierten Buchungen an

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
Ich habe eine Python-Flask-App mit einer PostgreSQL Datenbank für ein Barsystem mit den folgenden SQLAlchemy Models: 

class Mitglied(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text(), unique=False, nullable=False)
    nickname = db.Column(db.Text(), nullable=True)
    email = db.Column(db.Text(), nullable=True)
    guthaben = db.Column(db.Integer, default=0.0)
    blacklist = db.Column(db.Boolean, default=False)
    aktiv = db.Column(db.Boolean, nullable=False, default=True)
    verborgen = db.Column(db.Boolean, nullable=False, default=False)
    schwaerzungs_grenze = db.Column(db.Integer, nullable=True, default=MINDEST_GUTHABEN)
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
    reihenfolge = db.Column(db.Integer, nullable=True)
    aktiv = db.Column(db.Boolean, nullable=False, default=True)
    name = db.Column(db.Text, unique=True, nullable=False)
    preis = db.Column(db.Integer, nullable=False)
    buchungen = db.relationship(
        "Buchung", lazy=True
    )  # Stelle sicher, dass diese auch hier ist

    buchungen_von_artikel = db.relationship(
        "Buchung", back_populates="artikel_obj", lazy=True
    )

    def __repr__(self):
        return f"<Artikel {self.name} ({self.preis:.2f}€)>"


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
    abrechnungs_id = db.Column(
        db.Integer,
        db.ForeignKey("abrechnung.id"),
        nullable=True
    )

    beschreibung = db.Column(db.Text, nullable=True)
    menge = db.Column(db.Integer, nullable=False)
    preis_pro_einheit = db.Column(db.Integer, nullable=False)
    gesamtpreis = db.Column(db.Integer, nullable=False)
    zeitstempel = db.Column(db.DateTime, default=datetime.now, nullable=False)
    storniert = db.Column(
        db.DateTime, default=None, nullable=True
    )  # Wichtig für die Statistiken

    # Beziehungen zu anderen Modellen
    mitglied_obj = db.relationship("Mitglied", back_populates="buchungen_von_mitglied")
    artikel_obj = db.relationship("Artikel", back_populates="buchungen_von_artikel")
    abrechnung_obj = db.relationship(
        "Abrechnung",
        back_populates="buchungen"
    )

    def __repr__(self):
        return f"<Buchung {self.id} - {self.beschreibung}: {self.menge}x {self.artikel_obj.name if self.artikel_obj is not None else None} für {self.mitglied_obj.name}>"

class Abrechnung(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.Text, nullable=False)

    zeitstempel = db.Column(
        db.DateTime,
        default=datetime.now,
        nullable=False
    )

    buchungen = db.relationship(
        "Buchung",
        back_populates="abrechnung_obj",
        lazy=True
    )

    def __repr__(self):
        return f"<Abrechnung {self.id} {self.name}>"


Bitte schreibe mir eine SQL query die mir folgendes zurückgibt:
'''
