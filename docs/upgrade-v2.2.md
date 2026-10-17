# Upgrade auf v2.2

Von v2.1.0 auf v2.2. Hardening- und Bugfix-Release; **der Host-Port bleibt standardmäßig 80**, ist aber jetzt über `APP_PORT` in `.env` konfigurierbar; der interne Container-Port ist 4848 statt 5000.

## Neu & behoben

**Neu**
- `/healthz`: Health-Endpoint mit DB-Check und Versionsangabe (für Kiosk-Boot und Monitoring) (#22)
- `flask backup`: konsistentes, geprüftes `pg_dump` (gzip) nach `BACKUP_DIR` (Standard `/app/backups`) (#22)
- Tile-Cookie `tile_limit` enthält nun den Viewport (`n-WxH`) (#22)
- `APP_PORT` in `.env` (Standard 80) bestimmt den Host-Port; intern lauscht Gunicorn auf 4848 (#11)
- Footer wird nur noch im Admin-Bereich angezeigt (#24)

**Behoben**
- Excel-Import (#15): numerische Preis-Zellen funktionieren; `schwaerzungs_grenze` wird als Euro gelesen und in Cent gespeichert; Artikel-Import unterstützt `typ`, `volumen_liter`, `reinalkohol_liter`
- Berichte nach Restore (#25): Zeilenumbrüche werden beim Speichern und Restore normalisiert (kein `_x000D_` mehr im SQL); eine Migration repariert bereits gespeicherte Berichte
- Aussendungen/Auto-Aufbuchung (#27): Der Scheduler wird per Postgres-Advisory-Lock in genau einem Worker gestartet – auch nach einem Respawn eines Gunicorn-Workers läuft er nicht doppelt

## Breaking Changes

1. **Start wird bei Default-Secrets verweigert.** Bei `FLASK_DEBUG=False` startet die App nicht, wenn eines davon noch aktiv ist:
   - `FLASK_SECRET_KEY` = `supersecret` / `dev-secret-key-change-in-prod`
   - `DATABASE_PASSWORD` = `postgres` / `bibamus`
   - `ADMIN_PASSWORD` = `password` / `password!`

   Achtung: `ADMIN_PASSWORD` wird nur von `flask create-admin` gelesen. Wurde das Passwort in der App geändert, aber in `.env` blieb `password`, wird der Start trotzdem verweigert – in `.env` auf einen anderen Wert setzen (das ändert das bestehende Admin-Passwort nicht).
2. **Datenbank-Passwort ändern ist nicht trivial:** Das Postgres-Volume behält das alte Passwort. Entweder `ALTER USER <DATABASE_USERNAME> PASSWORD '...'` in der laufenden DB ausführen *bevor* `.env` geändert wird, oder (bei leerer DB) das Volume neu anlegen.

## Checkliste pro Standort

- [ ] `flask backup` ausführen und die Datei aus `./backups/` zusätzlich extern sichern: `docker compose exec app flask backup`
- [ ] Aktuelle Version notieren: `git log --oneline -n 1 | cat`
- [ ] `.env` prüfen: kein Default bei `FLASK_SECRET_KEY`, `DATABASE_PASSWORD`, `ADMIN_PASSWORD` (siehe oben)
- [ ] Update einspielen (unten)
- [ ] Kiosk-Unit: `ExecStartPre` auf `/healthz` umstellen, z. B.
      `ExecStartPre=/bin/sh -c 'until curl -sf -o /dev/null http://localhost/healthz; do sleep 2; done'`
- [ ] Optional: Host-Cron für Backups, z. B. `docker compose exec -T app flask backup`

## Update einspielen

`make prod-update` führt `git stash` und `git reset --hard origin/master` aus. Customizations in *untracked* Dateien bleiben erhalten; ein Konflikt beim `git stash pop` lässt das System halb aktualisiert zurück – daher **immer zuerst das Backup**.

```bash
docker compose exec app flask backup   # Backup (App läuft noch)
make prod-update                        # Update + Migrationen
curl -s http://localhost/healthz        # Prüfen: DB ok, neue Version
docker compose logs app | tail -50
```

Bei einem Fehlstart: Meldung im Log lesen (`Refusing to start with insecure default config` nennt die betroffene Variable), `.env` korrigieren, `docker compose up -d`.

## Rollback

`docker compose down`, `git reset --hard <notierte Version>`, Datenbank bei Bedarf aus dem Backup zurückspielen (die neue Migration `a7b8c9d0e1f2` ist reine Datenkorrektur und braucht kein Downgrade), `docker compose up --build -d`.
