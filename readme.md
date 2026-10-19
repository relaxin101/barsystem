# Barsystem
Dieses Projekt beherbergt eine einfache Python-Flask-Website zum Managen eines Barsystems mit Personenkonten.
Es umfasst u.a.:
- Konto-Blacklisting mit Schwärzung von Konten unter einem bestimmten Guthaben-Limit.
- Berichterstellung: Mittels SQL können eigene Berichte geschrieben, gespeichert und als Excel exportiert werden. Siehe [Nützliche Berichte](https://github.com/relaxin101/barsystem/edit/master/readme.md) für mehr Infox.
- Produkte & Mitglieder Bulk-Import: Excellisten mit entsprechenden Daten können zum Anlegen und Updaten von Produkten und Mitglieds-Konten benutzt werden. **Für Updates ist die Angabe der entsprechenden ID notwendig.**
- Hotlist von Mitgliedern: Auf der Homepage werden die Mitglieds-Konten, die in letzter Zeit viel gebucht haben, absteigend sortiert
- Suche: Eine Postgres-Volltextsuche hilft beim schnellen Finden durch Namen und optionale Spitznamen


## Installation
Zur Installation benötigst du [Docker](https://docs.docker.com/engine/install/) bzw. [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/)

Nachdem du das installiert hast, dupliziere das File `.env.example` und speichere es als `.env`. (Auf Windows ist etwas schwieriger weil du dabei Dateiart änderst und Windows das standardmäßig verhindert [Link](https://support.microsoft.com/en-us/windows/experience/storage-filemanagement/common-file-name-extensions-in-windows)) 
Die Datei `.env` enthält nun die (Standard-)Konfiguration der Website. Ändere am besten zunächst den Wert `FLASK_SECRET_KEY` auf einen zufälligen string (du brauchst ihn nachher nicht, das soll nur ein Geheimschlüssel sein den die App für diverse Hintergrunddinge benutzt). 
Mit `ADMIN_USERNAME`, `ADMIN_PASSWORD` konfigurierst du die Login-Daten für das Admin Panel, mit `MINDEST_GUTHABEN` setzt du das Limit, wie weit Personenkonten ins Minus gehen dürfen. Die restlichen Einstellungen kannst du nachlesen und ggf. entsprechend anpassen. 
_Versuche alles jetzt schon korrekt aufzusetzen, da einige Einstellungen in die Datenbank geschrieben werden und evt. nicht mehr leicht verändert werden können, ohne alle Daten zu löschen._

Jetzt kannst du die Website starten! Wenn du ein Terminal in dem Ordner öffnest (Windows: im File Explorer in den Ordner navigieren, STRG+SHIFT+Rechtsklick in den ordner und "Terminal öffnen" klicken) und `docker compose up -d --build` (+ ENTER) eintippst, beginnt docker mit der Installation der nötigen Komponenten und startet die Website automatisch. (Je nach Internet und Rechenleistung des Computers dauert das beim ersten Mal 5-15 min) Nun kannst du in dem lokalen Netzwerk unter der IP-Adresse des Computers die Website abrufen. Auf dem Computer wo das Ganze läuft, funktioniert auch [localhost](http://localhost). 

Ich empfehle beim Router eine statische IP mittels DHCP zu setzen - in einigen Routern kann man auch Namen vergeben sodass man dann im ganzen Netz unter __http://name-des-geraets__ die Barliste findet. Für Leute mit etwas IT-Ahnung ist sonst [mDNS](https://en.wikipedia.org/wiki/Multicast_DNS) eine angenehme Option.

### Updates
Um Updates zu bekommen musst du das repo mit [git](https://git-scm.com/) gecloned haben und nicht einfach nur runtergeladen haben. 
Dann empfiehlt es sich (semi-)regelmäßig in einem terminal die folgenden befehle auszuführen - notiere dir die aktuelle version der app `git log --oneline  -n 1 | cat`:

```bash
git log --oneline  -n 1 | cat 
docker compose down # Stoppe die App
git fetch # Checke nach updates
git add . && git stash # Um die customizations (Farben, Logo, etc.) etc. zu speichern und für git zu clearen
git reset --hard origin/master # Wendet die updates an
git stash pop # Um die customizations wiederherzustellen
docker compose up -d # Startet die App neu und führt ggf. Datenbank-Migrationen durch
```

**Caveat:** Auch wenn ich versuche alle Datenbank-Migrationen sauber durchzuführen empfiehlt es sich vor jedem Update ein Backup zu machen (siehe Bericht verwaltung).
Um das System gänzlich neu aufzusetzen, starte mit `docker compose down -v` - das stoppt die App und löscht auch die gesamte Datenbank - führe dann die restlichen Schritte durch und zum Schluss kannst du dann entsprechende Daten in den jeweiligen Admin-Panels importieren.


Alternativ: Wenn dein Betriebssystem MacOS oder Linux ist (oder `make` installiert hast), kannst du die app auch mit `make prod` starten und mit `make prod-update` updaten.


### Optionale Customization
Unter `static/css/style.css` können die Hauptfarben der Website angepasst werden:

```css
:root {
    --primary-light: #F0EDF8;       /* Hintergrund: helles Flieder */
    --primary-main: #6B5B9E;        /* Hauptfarbe: dunkles Flieder */
    --primary-hover: #574A85;       /* Hover */
    --primary-secondary: #D8D2EE;   /* Sekundär */
    --primary-accent: #9B8EC4;      /* Akzent */

    /* Admin-Panel Farbe */
    --admin-primary: #C8A432;       /* Hauptfarbe Sidebar/Topbar im Admin-Panel */

    /*... Sonstige Farben*/
}
```

Falls `static/img/logo.png` existiert, wird es im Header neben der Überschrift der Barliste angezeigt.

## Features
### Email Aussendungen
Mittels [Brevo](https://www.brevo.com/de/) können regelmäßige Aussendungen angelegt und verschickt werden.
Hierfür muss ein Brevo-Mail-Template angelegt werden, dass die parameter params.subject, params.recipient_name, params.amount (aktuelles guthaben) und params.message injected bekommt.

### Abrechnungen über einen bestimmten Zeitraum
Buchungen können zu Abrechnungen gruppiert werden um einen Überblick zu bekommen wie viel in einem bestimmten Zeitraum eingenommen wurde.

### Automatische Einzahlungen
Regelmäßiges prüfen eines Email Postfachs um Einzahlungen automatisch zu erkennen.

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
siehe [Assistent Prompt](./hilfreiches/barsystem_hilfe_assistent_prompt.md)
