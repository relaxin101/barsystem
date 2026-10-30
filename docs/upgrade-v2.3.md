# Upgrade auf v2.3 – Zeitzonen (#32), Einstellungen und Rollen (#38)

Alle Zeiten werden jetzt in Ortszeit angezeigt, eingegeben und ausgewertet – im Adminpanel, an der Bar, im Ranking, in Excel-Exporten und in gespeicherten Berichten. Vorher war überall UTC zu sehen, also im Sommer zwei Stunden und im Winter eine Stunde zu wenig.

Neu ist außerdem eine Seite „Einstellungen" und die Trennung in Admin und Superadmin.

## Neu & behoben

**Neu**
- `APP_TIMEZONE` in `.env` (Standard `Europe/Vienna`) legt die Ortszeit fest
- Einstellungen im Adminpanel, wirksam ohne Neustart (#38). Bestehende `.env`-Werte gelten weiter, bis jemand im Adminpanel einen anderen Wert speichert
- Rollen Admin und Superadmin, Seite „Benutzer" und „Passwort ändern" (#38)
- Name der Barliste und des Adminpanels als Einstellung statt fest im Template (#38)

**Behoben**
- Anzeige: Buchungen, Abrechnungen, Aussendungen, Bar und Ranking zeigen Ortszeit
- Eingaben: Datumsfilter und Abrechnungs-Zeiträume werden als Ortszeit gelesen
- Berichte: `zeitstempel`-Spalten werden automatisch umgerechnet, auch in `DATE()`, `TO_CHAR()` und Datumsvergleichen. Gespeicherte Berichte müssen dafür nicht geändert werden.

## Technische Änderung

Die Migration `b8c9d0e1f2a3` stellt `buchung.zeitstempel`, `buchung.storno_updated_at`, `abrechnung.zeitstempel` und `aussendung.last_run` auf `timestamp with time zone` um. Sie geht davon aus, dass die bestehenden Werte UTC sind, und die gespeicherten Zeitpunkte bleiben dabei unverändert. Die Datenbank-Session läuft in `APP_TIMEZONE`, daher rechnet Postgres selbst in Ortszeit um.

Das Excel-Backup (`/admin/export/db-backup`) speichert Zeitstempel weiterhin als UTC, die übrigen Excel-Exporte in Ortszeit.

Die Migration `c9d0e1f2a3b4` benennt die ungenutzte Spalte `user.is_admin` in `is_superadmin` um und legt die Tabelle `einstellung` an.

Berichte laufen über die eigene Datenbank-Rolle `bericht_leser`, die nur Fachtabellen lesen darf. `flask sync-report-role` legt sie an und läuft bei jedem Start in `db-init`, es ist also nichts zu tun. Das Passwort wird aus `FLASK_SECRET_KEY` abgeleitet. Neue Tabellen müssen in `REPORT_TABLES` (`utils/bericht_engine.py`) eingetragen werden, sonst sind sie in Berichten nicht sichtbar.

## Rollen

| | Admin | Superadmin |
|---|---|---|
| Tagesgeschäft (Buchungen, Guthaben, Abrechnungen, Artikel, Mitglieder, Aussendungen) | ja | ja |
| Berichte: SQL bearbeiten, ausführen, speichern, Excel | ja, nur lesend | ja, lesend |
| Berichte: Schreibzugriff | nein | per Häkchen, je Ausführung |
| Einstellungen „Allgemein" | ja | ja |
| Einstellungen Aussendungen und Auto-Aufbuchung, Systemwerte | nein | ja |
| Benutzer verwalten | nein | ja |
| Excel-Backup und Restore | ja, ohne Benutzerkonten und Einstellungen | ja, alle Tabellen |

Das bestehende Konto bleibt ein normaler Admin, weil mehrere Personen sein Passwort kennen. Ein Superadmin wird am Host angelegt.

Zugangsdaten (`BREVO_SECRET`, `IMAP_*`), Datenbank-Werte, `FLASK_SECRET_KEY` und `APP_TIMEZONE` bleiben in der `.env`. Sie landen sonst in jedem Datenbank-Backup bzw. werden gebraucht, bevor die Datenbank erreichbar ist. Superadmins sehen sie auf der Seite „Einstellungen", Zugangsdaten nur als „gesetzt" oder „fehlt".

## Verhaltensänderungen

1. **Bericht „Anwesenheit" und andere Auswertungen pro Tag:** `DATE(zeitstempel)` trennt jetzt um Mitternacht Ortszeit, vorher um 02:00 (Sommer) bzw. 01:00 (Winter). Wer von 23:30 bis 00:30 da war, steht nun an zwei Tagen in der Liste. Soll pro Barabend gezählt werden, braucht der Bericht einen eigenen Tageswechsel, z. B. um 06:00:
   ```sql
   DATE(b.zeitstempel - interval '6 hours') AS datum
   ```
2. **Berichte mit festem Datum** (z. B. Chargenrabatt): `BETWEEN '2026-07-09' AND '2026-10-13'` gilt jetzt ab Mitternacht Ortszeit. Wiederholt man einen alten Bericht, können Buchungen knapp an der Grenze anders zugeordnet werden.
3. **Alte Excel-Backups** lassen sich nach der Migration nicht mehr einspielen, weil die Datenbankversion nicht mehr übereinstimmt (das gilt für jede Migration).
4. **SQL in Berichten kann nichts mehr ändern.** `UPDATE`, `DELETE` usw. schlagen fehl und die Tabellen `user` und `einstellung` sind nicht lesbar. Wer Daten per SQL korrigieren muss, braucht einen Superadmin und das Häkchen „Mit Schreibzugriff ausführen". Gespeicherte Berichte, die nur lesen, laufen unverändert.
5. **Excel-Backup als Admin** enthält keine Benutzerkonten und Einstellungen mehr. Für ein vollständiges Backup als Superadmin anmelden oder `flask backup` verwenden.
6. **Angepasste Namen im Template:** Wurden `Ergo Bibamus!` oder `Creotorium` in `templates/base.html` geändert, kann `git stash pop` beim Update einen Konflikt melden. Dann die neue Version der Datei übernehmen und die Namen unter „Einstellungen" eintragen.
7. **Auto-Aufbuchung bucht nur noch bestätigte Mails.** Der From-Header lässt sich fälschen, deshalb muss der eigene Mailserver die Domain aus `AUTO_SENDER` per DKIM oder DMARC bestätigen (oberster Header `Authentication-Results`). `AUTO_SENDER` ist damit Pflicht, ohne den Wert läuft der Job nicht. Setzt der Mailserver den Header nicht, wird keine Mail mehr gebucht.
8. **Auto-Aufbuchung braucht den exakten Namen.** Name oder einer der Spitznamen muss genau passen (Groß-/Kleinschreibung egal). „Max" trifft nicht mehr „Maximilian". Mails ohne Treffer werden wie bisher als gelesen markiert und nur im Log vermerkt: das Guthaben muss dann von Hand aufgebucht werden.
9. **Aussendungen laufen im Hintergrund.** „Jetzt senden" bei einer gespeicherten Aussendung geht innerhalb einer Minute über den Scheduler raus, der Versand über das Formular läuft ab dem Klick im Hintergrund. Das Ergebnis steht deshalb nicht mehr in der Meldung, sondern im Log (Formular) bzw. in der Spalte „letzter Lauf". Bricht ein Versand ab, bekommen die restlichen Mitglieder diese Aussendung nicht; doppelt verschickt wird sie nicht.

## Checkliste pro Standort

- [ ] `flask backup` ausführen und die Datei aus `./backups/` zusätzlich extern sichern: `docker compose exec app /app/.venv/bin/flask backup`
- [ ] Aktuelle Version notieren: `git log --oneline -n 1 | cat`
- [ ] **Vor dem Update prüfen, dass der Container in UTC läuft:** `docker compose exec app date`. Die Ausgabe muss `UTC` zeigen. Steht dort eine andere Zeitzone (z. B. weil `TZ` in `.env` gesetzt ist), enthält die Datenbank Ortszeiten und die Migration würde sie verschieben – dann **nicht** updaten, sondern zuerst klären.
- [ ] Gespeicherte Berichte nach bestehenden Umrechnungen durchsuchen, also `AT TIME ZONE` oder `+ interval`. Solche Korrekturen rechnen die Zeit nach dem Update doppelt um und müssen entfernt werden.
- [ ] Bei einem Standort außerhalb Österreichs: `APP_TIMEZONE` in `.env` setzen
- [ ] **Bei Auto-Aufbuchung vor dem Update eine echte Bank-Mail prüfen:** im Mailprogramm „Quelltext anzeigen". Der oberste `Authentication-Results`-Header muss vom eigenen Mailserver stammen und `dkim=pass` mit `header.d=` oder `header.i=` der Bank-Domain bzw. `dmarc=pass` mit `header.from=` der Bank-Domain enthalten. `AUTO_SENDER` muss dieselbe Domain haben. Fehlt das, **nicht updaten**: Bank-Mails würden als gelesen markiert, aber nicht gebucht.
- [ ] Update einspielen (unten)
- [ ] Superadmin anlegen (unten). Bis dahin läuft alles normal aus der `.env`, nur Aussendungs- und Auto-Aufbuchungs-Einstellungen, Benutzerverwaltung und Schreibzugriff in Berichten sind nicht erreichbar
- [ ] Prüfen, ob `admin` ein neues Passwort bekommen soll, z. B. wenn es Personen kennen, die nicht mehr im Amt sind

## Update einspielen

```bash
docker compose exec app /app/.venv/bin/flask backup   # Backup (App läuft noch)
docker compose exec app date           # Muss UTC zeigen
make prod-update                        # Update + Migrationen
curl -s http://localhost/healthz        # Prüfen: DB ok, neue Version
docker compose logs app | tail -50
```

Danach im Adminpanel eine neue Buchung ansehen: Die Uhrzeit muss der aktuellen Ortszeit entsprechen.

Superadmin anlegen (fragt nach dem Passwort):

```bash
docker compose exec app /app/.venv/bin/flask auth create-superadmin --username <name>
```

Danach unter „Berichte" einen gespeicherten Bericht öffnen. Erscheint „Berichte-Zugang ist nicht eingerichtet", fehlt die Datenbank-Rolle: `docker compose exec app /app/.venv/bin/flask sync-report-role`.

## Rollback

Die Migration muss zuerst zurückgenommen werden, solange der neue Code noch im Container liegt:

```bash
docker compose exec app /app/.venv/bin/flask db downgrade a7b8c9d0e1f2
docker compose down
git reset --hard <notierte Version>
docker compose up --build -d
```

Das Downgrade stellt die Spalten wieder auf UTC ohne Zeitzone um, Buchungen bleiben erhalten. Einstellungen aus dem Adminpanel gehen dabei verloren, die `.env` gilt dann wieder. Zusätzlich angelegte Benutzer bleiben bestehen und müssen bei Bedarf entfernt werden. Alternativ die Datenbank aus dem Backup zurückspielen; damit gehen Buchungen seit dem Update verloren.
