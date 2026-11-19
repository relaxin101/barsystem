# Upgrade auf v2.3: Zeitzonen (#32), Einstellungen und Rollen (#38), Compacting

Von v2.2 auf v2.3. Die wichtigsten Änderungen:

- **Ortszeit:** Alle Zeiten werden jetzt in Ortszeit angezeigt, eingegeben und ausgewertet. Das gilt im Adminpanel, an der Bar, im Ranking, in Excel-Exporten und in gespeicherten Berichten. Vorher war überall UTC zu sehen, im Sommer also zwei Stunden und im Winter eine Stunde zu wenig.
- **Einstellungen und Rollen:** Es gibt eine Seite „Einstellungen“ und die Trennung in User und Superuser.
- **Compacting:** Damit lässt sich die Datenbank verkleinern.
- **Tabellen:** Alle Tabellen im Adminpanel lassen sich durchsuchen und sortieren.

Die vollständige Liste der Änderungen steht im [CHANGELOG](../CHANGELOG.md).

## Neu & behoben

**Neu**
- `APP_TIMEZONE` in `.env` (Standard `Europe/Vienna`) legt die Ortszeit fest.
- Einstellungen im Adminpanel, wirksam ohne Neustart (#38). Bestehende `.env`-Werte gelten weiter, bis jemand im Adminpanel einen anderen Wert speichert. Jeder Abschnitt wird einzeln gespeichert und warnt vor ungespeicherten Änderungen.
- Rollen User und Superuser, Seiten „Benutzer“ und „Passwort ändern“ (#38).
- Berichte: Gespeicherte Berichte lassen sich umbenennen, ihre Abfrage lässt sich ändern. Eine geänderte Abfrage muss zuerst mit „Bericht testen“ fehlerfrei laufen, erst dann lässt sie sich speichern.
- Tabellen im Adminpanel: Suchfeld, Sortieren per Klick auf den Spaltenkopf, Hinweis bei leeren Tabellen oder keinen Treffern. Ausgenommen sind die Buchungshistorie (seitenweise) und die Benutzerliste, sie werden nicht sortiert.
- **Compacting** (nur Superuser, Menüpunkt „Compacting“): Fasst alle Abrechnungen eines Zeitraums zu einer Abrechnung mit einer Saldo-Zeile pro Mitglied zusammen. So funktioniert es:
  - Die Guthaben bleiben gleich. Stornierte Buchungen fallen weg.
  - Auf Wunsch werden danach nicht mehr verwendete Artikel und Mitglieder mit Guthaben € 0,00 gelöscht.
  - Vorher gibt es einen Excel-Bericht mit Summen, Konsum pro Artikel und, pro Mitglied, Summen, Anwesenheitstagen und Mengen.
  - **Das Compacting lässt sich nicht rückgängig machen.** Vorher ein Backup ziehen, auf der Prüfseite gibt es dafür einen Button.

**Behoben**
- Anzeige: Buchungen, Abrechnungen, Aussendungen, Bar und Ranking zeigen Ortszeit.
- Eingaben: Datumsfilter und Abrechnungs-Zeiträume werden als Ortszeit gelesen.
- Berichte: `zeitstempel`-Spalten werden automatisch umgerechnet, auch in `DATE()`, `TO_CHAR()` und Datumsvergleichen. Gespeicherte Berichte müssen dafür nicht geändert werden.
- Gleichzeitige Buchungen am Kiosk und im Adminpanel überschreiben das Guthaben nicht mehr gegenseitig. Der Buchen-Button reagiert nur auf den ersten Tipp.
- Fehler beim Buchen zeigen dem Gast keine technischen Details mehr, sie stehen im Log.
- Abrechnung-Detail: Stornierte Buchungen zählen nicht mehr in den Kontensummen (#42).
- Die Abrechnungsliste zeigt auch Abrechnungen ohne Buchungen.
- „Bis“-Zeiten schließen die ganze Minute ein: „bis 23:59“ enthält auch eine Buchung um 23:59:30. Das gilt für Abrechnungen, die Buchungshistorie und den Excel-Export. „Abrechnung ändern“ verliert außerdem die letzte Buchung nicht mehr.
- Nach einem Restore schlägt die erste neue Buchung nicht mehr fehl.
- Der Guthaben-Import nennt Mitglieds-IDs, die er nicht buchen konnte.
- Die Kiosk-Startseite lädt schneller, weil die Mitgliederliste nicht mehr doppelt berechnet wird.

## Technische Änderung

Die Migration `b8c9d0e1f2a3` stellt `buchung.zeitstempel`, `buchung.storno_updated_at`, `abrechnung.zeitstempel` und `aussendung.last_run` auf `timestamp with time zone` um. Sie geht davon aus, dass die bestehenden Werte UTC sind. Die gespeicherten Zeitpunkte bleiben dabei unverändert. Die Datenbank-Session läuft in `APP_TIMEZONE`, deshalb rechnet Postgres selbst in Ortszeit um.

Das Excel-Backup (`/admin/export/db-backup`) speichert Zeitstempel weiterhin als UTC, die übrigen Excel-Exporte in Ortszeit.

Die Migration `c9d0e1f2a3b4` benennt die ungenutzte Spalte `user.is_admin` in `is_superuser` um und legt die Tabelle `einstellung` an.

Berichte laufen über die eigene Datenbank-Rolle `bericht_leser`, die nur Fachtabellen lesen darf. `flask sync-report-role` legt sie an und läuft bei jedem Start in `db-init`, es ist also nichts zu tun. Das Passwort wird aus `FLASK_SECRET_KEY` abgeleitet. Neue Tabellen müssen in `REPORT_TABLES` (`utils/bericht_engine.py`) eingetragen werden, sonst sind sie in Berichten nicht sichtbar.

## Rollen

| | User | Superuser |
|---|---|---|
| Tagesgeschäft (Buchungen, Guthaben, Abrechnungen, Artikel, Mitglieder, Aussendungen) | ja | ja |
| Berichte: SQL bearbeiten, ausführen, speichern, Excel | ja, nur lesend | ja, lesend |
| Berichte: Schreibzugriff | nein | per Häkchen, je Ausführung |
| Einstellungen „Allgemein“ | ja | ja |
| Einstellungen Aussendungen und Auto-Aufbuchung, Systemwerte | nein | ja |
| Benutzer verwalten | nein | ja |
| Compacting | nein | ja |
| Excel-Backup und Restore | ja, ohne Benutzerkonten und Einstellungen | ja, alle Tabellen |

Der Login aus der `.env` (`ADMIN_USERNAME`) wird beim Start automatisch Superuser. Alle anderen bestehenden Konten sind nach dem Update normale User. Ein Superuser kann sie unter „Benutzer“ hochstufen oder neue Konten anlegen.

Zugangsdaten (`BREVO_SECRET`, `IMAP_*`), Datenbank-Werte, `FLASK_SECRET_KEY` und `APP_TIMEZONE` bleiben in der `.env`. Sonst würden sie in jedem Datenbank-Backup landen, und manche werden gebraucht, bevor die Datenbank erreichbar ist. Superuser sehen sie auf der Seite „Einstellungen“, Zugangsdaten nur als „gesetzt“ oder „fehlt“.

## Verhaltensänderungen

1. **Bericht „Anwesenheit“ und andere Auswertungen pro Tag:** `DATE(zeitstempel)` trennt jetzt um Mitternacht Ortszeit, vorher um 02:00 (Sommer) bzw. 01:00 (Winter). Wer von 23:30 bis 00:30 da war, steht nun an zwei Tagen in der Liste. Soll pro Barabend gezählt werden, braucht der Bericht einen eigenen Tageswechsel, z. B. um 06:00:
   ```sql
   DATE(b.zeitstempel - interval '6 hours') AS datum
   ```
2. **Berichte mit festem Datum** (z. B. Chargenrabatt): `BETWEEN '2026-07-09' AND '2026-10-13'` gilt jetzt ab Mitternacht Ortszeit. Wiederholt man einen alten Bericht, können Buchungen knapp an der Grenze anders zugeordnet werden.
3. **Alte Excel-Backups** lassen sich nach der Migration nicht mehr einspielen, weil die Datenbankversion nicht mehr übereinstimmt. Das gilt für jede Migration.
4. **SQL in Berichten kann nichts mehr ändern.** `UPDATE`, `DELETE` usw. schlagen fehl, und die Tabellen `user` und `einstellung` sind nicht lesbar. Wer Daten per SQL korrigieren muss, braucht einen Superuser und das Häkchen „Mit Schreibzugriff ausführen“. Gespeicherte Berichte, die nur lesen, laufen unverändert.
5. **Excel-Backup als User** enthält keine Benutzerkonten und Einstellungen mehr. Für ein vollständiges Backup als Superuser anmelden oder `flask backup` verwenden.
6. **Angepasste Namen im Template:** Wurden `Ergo Bibamus!` oder `Creotorium` in `templates/base.html` geändert, kann `git stash pop` beim Update einen Konflikt melden. `base.html` hat sich in dieser Version geändert. Dann die neue Version der Datei übernehmen und die Namen dort wieder eintragen.
7. **Auto-Aufbuchung:**
   - `AUTO_SENDER` ist jetzt Pflicht. Ohne Wert läuft der Job nicht.
   - Geprüft wird nur der Absender-Header der Mail. Ob die Mail wirklich von der Bank kommt, prüft das System nicht.
   - Der Name aus der Mail wird als Teil des Namens oder Spitznamens gesucht: „Max“ trifft auch „Maximilian“. Gibt es mehrere Treffer, wird auf das alphabetisch erste Mitglied gebucht und eine Warnung ins Log geschrieben.
   - Mails ohne Treffer werden wie bisher als gelesen markiert und nur im Log vermerkt. Das Guthaben muss dann von Hand aufgebucht werden.
8. **Aussendungen laufen im Hintergrund.**
   - „Jetzt senden“ bei einer gespeicherten Aussendung geht innerhalb einer Minute über den Scheduler raus. Der Versand über das Formular läuft ab dem Klick im Hintergrund.
   - Das Ergebnis steht deshalb nicht mehr in der Meldung, sondern im Log (Formular) bzw. in der Spalte „letzter Lauf“.
   - Bricht ein Versand ab, bekommen die restlichen Mitglieder diese Aussendung nicht. Doppelt verschickt wird sie nicht.
9. **„Bis“ zählt die ganze Minute.** Eine Abrechnung „bis 20:00“ enthält jetzt auch Buchungen bis 20:00:59. Eine neue Abrechnung kann dadurch ein paar Buchungen mehr enthalten als früher.
10. **Befehle am Host umbenannt:**
    - `flask create-admin` heißt jetzt `flask auth create-default-user`.
    - `flask auth change-admin-password` heißt jetzt `flask auth change-password`.
    - Neu ist `flask auth create-user [--superuser]`.
    - `docker-compose.yml` ist angepasst. Eigene Skripte oder Cronjobs mit den alten Namen müssen geändert werden.
11. **Entfernt:** `/admin/export/mitglieder` und `/admin/export/produkte`. Sie waren nirgends verlinkt, `/produkte` funktionierte nicht. Stammdaten gibt es über Berichte, z. B. `SELECT * FROM mitglied`.

## Checkliste pro Standort

- [ ] `flask backup` ausführen und die Datei aus `./backups/` zusätzlich extern sichern: `docker compose exec app /app/.venv/bin/flask backup`
- [ ] Aktuelle Version notieren: `git log --oneline -n 1 | cat`
- [ ] **Vor dem Update prüfen, dass der Container in UTC läuft:** `docker compose exec app date`. Die Ausgabe muss `UTC` zeigen. Steht dort eine andere Zeitzone, z. B. weil `TZ` in `.env` gesetzt ist, enthält die Datenbank Ortszeiten, und die Migration würde sie verschieben. Dann **nicht** updaten, sondern zuerst klären.
- [ ] Gespeicherte Berichte nach bestehenden Umrechnungen durchsuchen, also `AT TIME ZONE` oder `+ interval`. Solche Korrekturen rechnen die Zeit nach dem Update doppelt um und müssen entfernt werden.
- [ ] Bei einem Standort außerhalb Österreichs: `APP_TIMEZONE` in `.env` setzen.
- [ ] Bei Auto-Aufbuchung: `AUTO_SENDER` in `.env` gesetzt? Ohne den Wert bucht der Job nach dem Update nichts mehr.
- [ ] Eigene Skripte oder Cronjobs nach `create-admin` und `change-admin-password` durchsuchen (siehe Punkt 10).
- [ ] Update einspielen (unten).
- [ ] Mit dem Login aus der `.env` anmelden: Unter „Benutzer“ ist er Superuser. Weitere Konten bei Bedarf hochstufen.
- [ ] Prüfen, ob der Login aus der `.env` ein neues Passwort bekommen soll, z. B. wenn es Personen kennen, die nicht mehr im Amt sind. Er hat jetzt alle Rechte.

## Update einspielen

```bash
docker compose exec app /app/.venv/bin/flask backup   # Backup (App läuft noch)
docker compose exec app date           # Muss UTC zeigen
make prod-update                        # Update + Migrationen
curl -s http://localhost/healthz        # Prüfen: DB ok, neue Version
docker compose logs app | tail -50
```

Danach im Adminpanel eine neue Buchung ansehen: Die Uhrzeit muss der aktuellen Ortszeit entsprechen.

Weiteren Superuser am Host anlegen (optional, fragt nach dem Passwort):

```bash
docker compose exec app /app/.venv/bin/flask auth create-user --superuser --username <name>
```

Danach unter „Berichte“ einen gespeicherten Bericht öffnen. Erscheint „Berichte-Zugang ist nicht eingerichtet“, fehlt die Datenbank-Rolle: `docker compose exec app /app/.venv/bin/flask sync-report-role`.

## Rollback

Die Migration muss zuerst zurückgenommen werden, solange der neue Code noch im Container liegt:

```bash
docker compose exec app /app/.venv/bin/flask db downgrade a7b8c9d0e1f2
docker compose down
git reset --hard <notierte Version>
docker compose up --build -d
```

Was das Downgrade bewirkt:
- Die Spalten werden wieder auf UTC ohne Zeitzone umgestellt. Buchungen bleiben erhalten.
- Einstellungen aus dem Adminpanel gehen verloren, dann gilt wieder die `.env`.
- Zusätzlich angelegte Benutzer bleiben bestehen und müssen bei Bedarf entfernt werden.
- Ein ausgeführtes Compacting bleibt bestehen. Die zusammengefassten Buchungen kommen nur über ein Backup zurück.

Alternativ die Datenbank aus dem Backup zurückspielen. Dann gehen die Buchungen seit dem Update verloren.
