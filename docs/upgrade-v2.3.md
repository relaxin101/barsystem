# Upgrade auf v2.3 – Zeitzonen (#32)

Alle Zeiten werden jetzt in Ortszeit angezeigt, eingegeben und ausgewertet – im Adminpanel, an der Bar, im Ranking, in Excel-Exporten und in gespeicherten Berichten. Vorher war überall UTC zu sehen, also im Sommer zwei Stunden und im Winter eine Stunde zu wenig.

## Neu & behoben

**Neu**
- `APP_TIMEZONE` in `.env` (Standard `Europe/Vienna`) legt die Ortszeit fest

**Behoben**
- Anzeige: Buchungen, Abrechnungen, Aussendungen, Bar und Ranking zeigen Ortszeit
- Eingaben: Datumsfilter und Abrechnungs-Zeiträume werden als Ortszeit gelesen
- Berichte: `zeitstempel`-Spalten werden automatisch umgerechnet, auch in `DATE()`, `TO_CHAR()` und Datumsvergleichen. Gespeicherte Berichte müssen dafür nicht geändert werden.

## Technische Änderung

Die Migration `b8c9d0e1f2a3` stellt `buchung.zeitstempel`, `buchung.storno_updated_at`, `abrechnung.zeitstempel` und `aussendung.last_run` auf `timestamp with time zone` um. Sie geht davon aus, dass die bestehenden Werte UTC sind, und die gespeicherten Zeitpunkte bleiben dabei unverändert. Die Datenbank-Session läuft in `APP_TIMEZONE`, daher rechnet Postgres selbst in Ortszeit um.

Das Excel-Backup (`/admin/export/db-backup`) speichert Zeitstempel weiterhin als UTC, die übrigen Excel-Exporte in Ortszeit.

## Verhaltensänderungen

1. **Bericht „Anwesenheit" und andere Auswertungen pro Tag:** `DATE(zeitstempel)` trennt jetzt um Mitternacht Ortszeit, vorher um 02:00 (Sommer) bzw. 01:00 (Winter). Wer von 23:30 bis 00:30 da war, steht nun an zwei Tagen in der Liste. Soll pro Barabend gezählt werden, braucht der Bericht einen eigenen Tageswechsel, z. B. um 06:00:
   ```sql
   DATE(b.zeitstempel - interval '6 hours') AS datum
   ```
2. **Berichte mit festem Datum** (z. B. Chargenrabatt): `BETWEEN '2026-07-09' AND '2026-10-13'` gilt jetzt ab Mitternacht Ortszeit. Wiederholt man einen alten Bericht, können Buchungen knapp an der Grenze anders zugeordnet werden.
3. **Alte Excel-Backups** lassen sich nach der Migration nicht mehr einspielen, weil die Datenbankversion nicht mehr übereinstimmt (das gilt für jede Migration).

## Checkliste pro Standort

- [ ] `flask backup` ausführen und die Datei aus `./backups/` zusätzlich extern sichern: `docker compose exec app flask backup`
- [ ] Aktuelle Version notieren: `git log --oneline -n 1 | cat`
- [ ] **Vor dem Update prüfen, dass der Container in UTC läuft:** `docker compose exec app date`. Die Ausgabe muss `UTC` zeigen. Steht dort eine andere Zeitzone (z. B. weil `TZ` in `.env` gesetzt ist), enthält die Datenbank Ortszeiten und die Migration würde sie verschieben – dann **nicht** updaten, sondern zuerst klären.
- [ ] Gespeicherte Berichte nach bestehenden Umrechnungen durchsuchen, also `AT TIME ZONE` oder `+ interval`. Solche Korrekturen rechnen die Zeit nach dem Update doppelt um und müssen entfernt werden.
- [ ] Bei einem Standort außerhalb Österreichs: `APP_TIMEZONE` in `.env` setzen
- [ ] Update einspielen (unten)

## Update einspielen

```bash
docker compose exec app flask backup   # Backup (App läuft noch)
docker compose exec app date           # Muss UTC zeigen
make prod-update                        # Update + Migrationen
curl -s http://localhost/healthz        # Prüfen: DB ok, neue Version
docker compose logs app | tail -50
```

Danach im Adminpanel eine neue Buchung ansehen: Die Uhrzeit muss der aktuellen Ortszeit entsprechen.

## Rollback

Die Migration muss zuerst zurückgenommen werden, solange der neue Code noch im Container liegt:

```bash
docker compose exec app uv run flask db downgrade a7b8c9d0e1f2
docker compose down
git reset --hard <notierte Version>
docker compose up --build -d
```

Das Downgrade stellt die Spalten wieder auf UTC ohne Zeitzone um und verliert keine Daten. Alternativ die Datenbank aus dem Backup zurückspielen; damit gehen Buchungen seit dem Update verloren.
