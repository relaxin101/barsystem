# Manual test checklist (`ergo-bibamus` vs `master`)

The branch is 10 commits ahead of `master` (27 files changed). This covers what automated tests can't: real Postgres, Docker, gunicorn and the kiosk browser. Riskiest items first. Run everything against a copy of a real database, not a fresh one.

## 1. Scheduler lock (#27), not tested against real Postgres
- [ ] `docker compose up --build -d`, then `docker compose logs app`. Exactly one worker should log scheduler startup, and a minute later each job should log once per run, not four times.
- [ ] Find the worker that holds the lock and kill it. Look for the line `Booting worker with pid`, or run `docker compose exec app ps aux | grep gunicorn`. Confirm gunicorn respawns the worker and the scheduler resumes.
- [ ] Kill a worker that does *not* hold the lock. Confirm no second scheduler starts and jobs still run once per run.
- [ ] Optional: `SELECT * FROM pg_locks WHERE locktype='advisory' AND objid=727272;` should return exactly one row.
- [ ] `make dev` (the `__main__` path) still starts the scheduler.
- [ ] Known gap: if the lock holder dies, the lock is only retaken when a worker (including its respawn) calls `start_scheduler`. Check that the respawn takes it.

## 2. Excel import (#15)
- [ ] Artikel import with numeric price cells (`2.5`, `3`) gives 250 and 300 cents.
- [ ] Artikel import with text prices (`"2,50"`, `"1.234,56"`) still works.
- [ ] The Artikel import modal shows the new fields `typ`, `volumen_liter` and `reinalkohol_liter`. Map them and check the values land correctly, then re-import with the ID to confirm updates work.
- [ ] Mitglieder import with `schwaerzungs_grenze` `-5` shows €-5.00 in the member list, and `-2,50` as text shows €-2.50.
- [ ] Re-import a file with an empty Grenze cell. The result should be "Kein Limit", not an error.
- [ ] After an import, a new member or Artikel can still be created in the UI. This checks that the id sequence reset (`setval`) works on real Postgres.

## 3. Berichte and restore (#25)
- [ ] Create a Bericht with a multi-line SQL query that has Windows line endings (paste it from Windows). Run it, then back it up via `/admin/export/db-backup`.
- [ ] Restore that backup into a DB with the Bericht deleted. The SQL should contain no `_x000D_` and the Bericht should run.
- [ ] Migration: before upgrading, put a Bericht in the DB with `_x000D_` or `\r\n` in its SQL (an old restore will have one). Run `flask db upgrade` and check the row is clean. Also check `flask db heads` shows a single head, `a7b8c9d0e1f2`.
- [ ] Check the migration's `LIKE '%\_x000D\_%'` escaping really matches rows on Postgres, since the unit tests ran on SQLite.
- [ ] A full restore still works for the other tables. Check that Aussendung messages are unchanged apart from the `_x000D_` fix.

## 4. Config check (breaking change)
- [ ] With the default `.env.example` copied unchanged, the app refuses to start and the log names each variable.
- [ ] After setting real values for all three, it starts. `ADMIN_USERNAME=admin` should only produce a warning.
- [ ] With the old `SECRET_KEY` name in `.env` and no `FLASK_SECRET_KEY`, it starts and logs a deprecation warning.
- [ ] `make dev` (`FLASK_DEBUG=True`) is not blocked by default secrets.
- [ ] Database password change: confirm the guide's `ALTER USER` advice works on a real volume.

## 5. `/healthz` and kiosk (#22)
- [ ] `curl -s localhost/healthz` returns `{"status":"ok","version":"<sha>"}`. The version should be the real commit if you build with `GIT_SHA=$(git rev-parse --short HEAD) docker compose up --build -d`, and `unknown` otherwise.
- [ ] `docker compose stop db`, then `/healthz` returns 503. Start the DB again and it recovers.
- [ ] `/healthz` polls don't show in the access log.
- [ ] The kiosk systemd unit with `ExecStartPre` polling `/healthz` waits for the DB at boot and doesn't start Chromium on an error page.
- [ ] Tile cookie: open the Barliste and check the cookie is `tile_limit=<n>-<W>x<H>`. Resize the window or rotate the screen and the count is re-measured. An old plain-number cookie is ignored and replaced.

## 6. `flask backup` (#22)
- [ ] `docker compose exec app flask backup` writes `barsystem_<ts>.sql.gz` to `./backups/` on the host.
- [ ] `gunzip -c` the file and restore it into a scratch DB to confirm it's complete.
- [ ] With the wrong DB password the command exits 1 and leaves no partial file.
- [ ] Host cron one-liner (`docker compose exec -T app flask backup`) works without a TTY.

## 7. Footer (#24) and general smoke test
- [ ] No footer on the Barliste, Buchen and Ranking pages. The footer shows in the admin area.
- [ ] Log in to admin. Do a booking, a Schwärzung, an Abrechnung and an Aufbuchung. Check the Ranking, the Hotlist and a manual Aussendung.
- [ ] Mixed names: `pyproject.toml` now says `EBS` and `2.1.0`, so check nothing user-facing broke.

## 8. Upgrade path (the real release test)
- [ ] On a copy of a v2.1.0 site: take a backup, run `make prod-update`, and confirm it comes up with migrations applied and customizations (`style.css`, logo) intact. The stash and pop can conflict.
- [ ] Walk through `docs/upgrade-v2.2.md` step by step and fix anything that doesn't match reality. Its commands haven't been run.
- [ ] `APP_PORT` is unset (default 80) so kiosk URLs shouldn't change; also test with `APP_PORT=4848` and update the kiosk URL.

## Things noticed
- `pyproject.toml` still says `version = "2.1.0"`. Bump it before tagging v2.2.0.
- `requirements.txt` is deleted on this branch (uv only). Make sure no deploy path still uses it.
- `prod-update` is a new Makefile target on this branch, so `master` doesn't have it until the branch is merged.
