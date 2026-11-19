# Changelog

Upgrade-Anleitungen pro Version stehen in [`docs/`](docs/).

## [2.3.0] – unveröffentlicht

Stand: Branch `creotorium`, 28 Commits vor `master` (v2.2.0). Anleitung für Standorte: [docs/upgrade-v2.3.md](docs/upgrade-v2.3.md).

### Neu
- **Zeitzonen (#32):** In der Datenbank liegt alles als `timestamptz` in UTC. Anzeige, Eingabe und Excel nutzen die Ortszeit aus `APP_TIMEZONE` (Standard `Europe/Vienna`). Die DB-Session läuft in dieser Zeitzone, deshalb rechnen gespeicherte Berichte ohne Änderung in Ortszeit. Helfer in `utils/zeit.py`, Typ `UTCDateTime` in `models.py`, Migration `b8c9d0e1f2a3`. (8981c76)
- **Seite „Einstellungen“ (#38):** Werte lassen sich ohne Neustart ändern. Reihenfolge: Wert in der DB, dann `.env`, dann Standard. Neue Tabelle `einstellung`, Definitionen in `utils/einstellungen.py`, Obergrenzen für Zahlen. Jeder Abschnitt hat ein eigenes Formular und warnt vor ungespeicherten Änderungen. (3f78f06, b6be9ea, 146fed6, 2d0131c)
- **Rollen User und Superuser (#38):** Neue Seite „Benutzer“ und „Passwort ändern“. Der Standarduser aus der `.env` ist immer Superuser. Migration `c9d0e1f2a3b4` benennt `user.is_admin` in `is_superuser` um. (3f78f06, eb46a76, 5ebf6cf)
- **Berichte nur lesend (#38):** Bericht-SQL läuft über die DB-Rolle `bericht_leser`, die nur die Tabellen aus `REPORT_TABLES` lesen darf. `flask sync-report-role` legt sie in `db-init` an, der Timeout liegt bei 25 s. Schreibzugriff gibt es nur für Superuser, per Häkchen und je Ausführung. (3f78f06, 57ad82c)
- **Berichte bearbeiten:** Gespeicherte Berichte lassen sich umbenennen. Eine geänderte Abfrage wird erst getestet und dann gespeichert, und der Server prüft sie vor dem Speichern noch einmal lesend. (b0c76bf, f5c8e2e)
- **Tabellen-Komponente:** Das Jinja-Makro `templates/macros/tabelle.html` mit `static/js/tabelle.js` bringt Suche, Sortierung per Spaltenkopf (`data-wert`), Leer- und Kein-Treffer-Zeile, klickbare Zeilen (`data-href`) und Auswahl-Checkboxen. Alle Admin-Tabellen nutzen es, außer Buchungshistorie und Benutzer, die nicht sortiert werden. (e849403, 7daea15)
- **Compacting (nur Superuser):** Abrechnungen, die vollständig in einem Zeitraum liegen, werden zu einer Saldo-Zeile pro Mitglied zusammengefasst. Nicht mehr referenzierte Artikel und Mitglieder mit Guthaben 0 können optional gelöscht werden. Vorher entsteht ein Excel-Bericht. Ein Fingerprint schützt vor Änderungen zwischen Prüfen und Ausführen. Code in `utils/compacting.py` und `blueprints/admin/compacting.py`. (9f5ccba)
- CSS-Klasse `form-schlicht` für Formulare ohne globalen Eingabe-Stil. (ebf587e)

### Geändert
- **Auth-CLI zusammengeführt:**
  - `flask create-admin` heißt jetzt `flask auth create-default-user`.
  - `flask auth change-admin-password` heißt jetzt `flask auth change-password`.
  - Neu ist `flask auth create-user [--superuser]`.
  - `db-init` und `make create-default-user` sind angepasst. (eb46a76)
- **Aussendungen laufen im Hintergrund.** Der Brevo-Request hat ein Timeout von 10 s, und `last_run` wird vor dem Versand gesetzt. (b6be9ea)
- **Auto-Aufbuchung:**
  - `AUTO_SENDER` ist jetzt Pflicht, sonst läuft der Job nicht.
  - Die DKIM/DMARC-Prüfung aus b6be9ea ist wieder entfernt, gefiltert wird nur der `From`-Header. (b6be9ea, 988d896, 96ff1e6)
  - Seit adb20d9 findet die Namenssuche wieder Teilstrings. Bei mehreren Treffern wird auf den ersten gebucht und eine Warnung geloggt. (adb20d9)
- **Bis-Zeitpunkte schließen die ganze Minute ein:** Das gilt für Abrechnung anlegen und ändern, die Buchungshistorie, den Excel-Export und das Compacting, über `utils.zeit.parse_local_ende`. Die Buchungshistorie endet standardmäßig bei „jetzt“. (e25bd56)
- Die Kiosk-Startseite `/` rechnet keine Hotlist mehr, die Kacheln kommen nur noch über `/api/members`. (166ef42)
- Der Ranking-Standard wird nicht mehr in die Session kopiert, eine Änderung erreicht also auch offene Kiosks. (b6be9ea)

### Behoben
- Gleichzeitige Buchungen, Aufbuchungen, Stornos und Auto-Aufbuchungen überschreiben das Guthaben nicht mehr gegenseitig, weil sie die Zeile sperren (`mitglied_sperren`). (57ad82c)
- Der Buchen-Button sperrt beim ersten Tipp. Fehler beim Buchen landen im Log und nicht mehr beim Gast. (57ad82c)
- „Abrechnung ändern“ verliert die letzte Buchung nicht mehr. (57ad82c)
- Nach einem Restore wird die ID-Sequenz korrekt gesetzt. (57ad82c)
- Der Guthaben-Import nennt übersprungene Mitglieds-IDs. (57ad82c)
- Die Kontensummen im Abrechnungs-Detail enthalten keine stornierten Buchungen mehr (#42). (b434983)
- Abrechnungen ohne Buchungen erscheinen wieder in der Abrechnungsliste. (51dc415)

### Entfernt
- `/admin/export/mitglieder`, `/admin/export/produkte` und `export_model_to_excel`. Beide Routen waren nirgends verlinkt, `/produkte` lieferte Fehler 500. (96ba3c2)

### Doku und Sonstiges
- Kiosk-Setup an die aktuelle Produktion angepasst, dazu das Stummschalten der Lautsprecher am Tablet. (a18e645, 9adf769)
- `.gitignore` ergänzt: `backups`, `barsystem.code-workspace`. (6b76536, 0994d5e)
- Die Doku nutzt `/app/.venv/bin/flask` im Container. (57ad82c)

### Bekannte Probleme
- **Auto-Aufbuchung, Namenssuche:** Code und Tests widersprechen sich. `test_partial_name_is_not_booked` und `test_ambiguous_member_match_skips_booking` in `tests/test_utils_auto_aufbuchung.py` erwarten die exakte Suche, die adb20d9 entfernt hat. Vor dem Release entscheiden: das Verhalten zurückholen (`_name_passt`) oder die Tests löschen.
- Die drei `create_backup`-Tests in `tests/test_backup.py` brauchen `pg_dump` lokal.
- Postgres-spezifisches SQL (Abrechnungsliste, `suche_mitglied`, `setval`) ist nicht automatisch getestet, weil die Tests mit SQLite laufen.
