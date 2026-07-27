# Barsystem Kiosk — Shuttle P51U Setup Guide

Ubuntu 26.04 LTS + Docker + Barsystem (local, off-grid) + Chromium kiosk (crash-proofed) + UFW (SSH + HTTP only).

Assumptions: admin user `admin`, kiosk user `kiosk`, hostname `barsystem`. Adjust as needed.

---

## 1. Ubuntu Installation

1. Download the **Ubuntu Desktop 26.04 LTS** ("Resolute Raccoon") ISO from ubuntu.com/download, and write it to a USB stick with **Rufus** (https://rufus.ie) — pick the ISO, leave the defaults (GPT / UEFI), and flash. (On Ubuntu/macOS you can use the built-in "Startup Disk Creator" / `dd` instead.)
2. P51U: USB keyboard + stick, power on, `F7`/`Del` for boot menu.
3. Install with:
   - **Minimal installation** — no office/games bloat (26.04 runs GNOME 50; the minimal profile keeps the low-power Celeron light)
   - Erase disk, install on the M.2/SSD
   - User `admin`, computer name `barsystem`
   - **No** automatic login for admin — the kiosk user gets that later
4. First boot:

```bash
sudo apt update && sudo apt full-upgrade -y && sudo reboot
```

## 2. Hostname

```bash
sudo hostnamectl set-hostname barsystem
```

`/etc/hosts` — local resolution must work or sudo stalls:

```
127.0.0.1   localhost
127.0.1.1   barsystem
::1         ip6-localhost ip6-loopback
```

Verify:

```bash
hostname -f              # barsystem
getent hosts barsystem   # 127.0.1.1
```

mDNS, so the LAN reaches the terminal as `barsystem.local`:

```bash
sudo apt install -y avahi-daemon
```

## 3. SSH

```bash
sudo apt install -y openssh-server
sudo systemctl enable --now ssh
```

Test from another machine: `ssh admin@barsystem.local`

## 4. Firewall — UFW

```bash
sudo apt install -y ufw
sudo ufw default deny incoming    # block everything inbound by default
sudo ufw default allow outgoing   # updates, docker pulls
sudo ufw allow OpenSSH            # port 22 — remote admin
sudo ufw allow 80/tcp             # Barsystem web
sudo ufw enable
sudo ufw status verbose           # expect: 22, 80, deny incoming
```

> **Docker caveat:** Docker-published ports bypass UFW. Fine for 80 (wanted), but anything else you publish is exposed too — the compose file below binds Postgres to `127.0.0.1` for exactly this reason.

## 5. Docker

```bash
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker admin     # docker without sudo; re-login required
sudo systemctl enable docker      # stack must come up on boot
```

Verify after re-login: `docker run --rm hello-world`

## 6. Barsystem Deployment (git clone, local = off-grid)

The full stack (Flask + Postgres) runs **on the terminal** in Docker; the kiosk uses `http://localhost` — no NAS, router, or internet needed. Clone with **git** (not a zip download) so updates work later.

```bash
sudo apt install -y git
sudo git clone https://github.com/relaxin101/barsystem.git /opt/barsystem
sudo chown -R admin:admin /opt/barsystem
cd /opt/barsystem
```

### 6.1 Configure `.env`

Copy the shipped template, then edit it:

```bash
cp .env.example .env
chmod 600 .env    # secrets: owner-readable only
```

**Minimal set you MUST change before the first start** (everything else has a working default):

- `FLASK_SECRET_KEY` — long random string; the default `supersecret`/`asdfasdfasdfasdf` is insecure. Generate one: `python3 -c "import secrets; print(secrets.token_hex(32))"`
- `DATABASE_USERNAME`, `DATABASE_PASSWORD`, `DATABASE_NAME` — pick your own DB credentials
- `ADMIN_USERNAME`, `ADMIN_PASSWORD` — the admin-panel login
- `MINDEST_GUTHABEN` — how far a member balance may go negative (e.g. `-50.0`)

> **Admin credentials are written into the database on the very first start and can't be changed easily afterwards** — get `ADMIN_USERNAME`/`ADMIN_PASSWORD` right before you first run `docker compose up`. (To redo them you must wipe the DB: `docker compose down -v`.)

The complete annotated file:

```bash
###################################
# Flask   (FLASK_SECRET_KEY is minimal — must change)
###################################
FLASK_SECRET_KEY=CHANGE_ME_RANDOM   # session/signing secret; long random string
FLASK_ALLOWED_HOSTS=*               # kiosk is localhost behind UFW, * is fine
FLASK_DEBUG=False                   # never True in production

###################################
# Database   (username/password/name are minimal — must change)
###################################
DATABASE_ENGINE=postgresql
DATABASE_NAME=barliste              # your DB name
DATABASE_USERNAME=CHANGE_ME         # your DB user
DATABASE_PASSWORD=CHANGE_ME_TOO     # your DB password
DATABASE_PORT=5432
DATABASE_HOST=db                    # docker-compose service name — DO NOT change

###################################
# Admin user   (all minimal — must change; written to DB on first start)
###################################
ADMIN_USERNAME=admin                # admin-panel login
ADMIN_PASSWORD=CHANGE_ME            # admin-panel password
MINDEST_GUTHABEN=-50.0              # lowest allowed balance (EUR)
RANKING_CONFIG_TTL_STUNDEN=12       # hotlist ranking cache lifetime (hours)
HOTLIST_DAYS=14                     # window for the "frequent bookers" hotlist
SCHWAERZUNGS_TEXT=Du bist geschwärzt!   # message shown on blacklisted accounts

###################################
# Brevo — email campaigns (optional; leave blank to disable)
###################################
BREVO_SECRET=                       # Brevo API key
BREVO_SENDER_MAIL=                  # verified sender address
BREVO_SENDER_NAME=                  # sender display name
BREVO_TEMPLATE=                     # numeric Brevo template ID

###################################
# IMAP — auto top-up from bank e-mails (optional)
# If IMAP_HOST / IMAP_USER / IMAP_PASSWORD are empty, the job is skipped.
###################################
IMAP_HOST=imap.example.com
IMAP_PORT=993
IMAP_USER=kasse@example.com
IMAP_PASSWORD=                      # mailbox password / app password

AUTO_SENDER=noreply@sparkasse.at    # only process mails from this sender (optional)
AUTO_BETREFF="Kontoeingang bei George"   # only mails whose subject contains this (optional)

# Regexes that pull the member and the amount out of the mail body:
AUTO_KONTO_REGEX="^.*Buchungstext:\\s*((Barschulden)|(BS))(.*)\\..*$"   # -> member name/email
AUTO_KONTO_GROUP=4                  # which capture group holds the member
AUTO_BETRAG_REGEX="^.*Sie haben soeben (.*) EUR auf Ihr Konto (\d*) erhalten\\..*$"   # -> amount
AUTO_BETRAG_GROUP=1                 # which capture group holds the amount
```

**Brevo** (email campaigns / Aussendungen): create a Brevo account, generate an API key → `BREVO_SECRET`, verify a sender → `BREVO_SENDER_MAIL`/`BREVO_SENDER_NAME`, and build a mail template whose ID goes in `BREVO_TEMPLATE`. The template must accept the params `subject`, `recipient_name`, `amount` (current balance) and `message`. Leave all four blank to keep the feature off.

**IMAP** (automatic top-ups): the app polls a mailbox and credits members when a matching bank-notification mail arrives. It stays disabled unless `IMAP_HOST`, `IMAP_USER` and `IMAP_PASSWORD` are all set. The two regexes extract *who* to credit and *how much* from the mail body — the defaults above match a Sparkasse/George notification; adjust them (and the `_GROUP` numbers) to your bank's wording. Use an app-specific password where the provider requires one.

### 6.2 Harden the shipped compose

The repo's `docker-compose.yml` publishes Postgres on `5432` to the whole LAN and sets no restart policy. Add an **override** (Docker merges it automatically) that closes the DB port and makes the stack self-heal — without editing the tracked file:

```bash
cat > /opt/barsystem/docker-compose.override.yml <<'EOF'
services:
  db:
    container_name: barsystem-db     # stable name for backup/restore commands
    restart: unless-stopped          # self-heal after crash/reboot
    ports: !reset []                 # drop the LAN-exposed 5432; app still reaches db over the internal network
  flask-app:
    restart: unless-stopped          # self-heal after crash/reboot
EOF
```

`!reset []` needs Docker Compose v2.24+ (the docker-ce installed above is newer). Keep the override out of git so `git reset --hard` during updates can't remove it:

```bash
printf 'docker-compose.override.yml\nbackups/\n' >> /opt/barsystem/.git/info/exclude
```

### 6.3 First start

Migrations run automatically (the repo's `db-init` service runs `flask db upgrade` before the app starts):

```bash
docker compose up -d --build   # first build takes 5-15 min
curl -I http://localhost       # expect HTTP 200/302
```

### 6.4 Updates (git pull)

Run occasionally from `/opt/barsystem`. Take a backup first (Appendix A runs one nightly anyway):

```bash
cd /opt/barsystem
docker compose down                  # stop the app
git fetch                            # check for updates
git add . && git stash               # park any local tracked changes
git reset --hard origin/master       # apply the update
docker compose up -d                 # restart + auto-run DB migrations
git stash pop                        # restore local tracked changes
```

Your `.env` (git-ignored) and `docker-compose.override.yml` (locally excluded in §6.2) are untouched by this, so credentials, the closed DB port and the restart policies all survive the update.

## 7. Kiosk User + Autologin

```bash
sudo adduser --disabled-password --gecos "Kiosk" kiosk
```

`/etc/gdm3/custom.conf`:

```ini
[daemon]
AutomaticLoginEnable=true      # boot straight into the kiosk session
AutomaticLogin=kiosk
# WaylandEnable stays default (on) — Wayland rotates touch input with the display
```

## 8. GNOME Kiosk Settings

Run as the kiosk user (log in once, or `sudo -u kiosk dbus-run-session gsettings ...`):

```bash
gsettings set org.gnome.desktop.session idle-delay 300                                   # screen off after 5 min (anti image-retention); any tap wakes it
gsettings set org.gnome.desktop.screensaver lock-enabled false                           # wake straight to the app, no lock screen
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing'   # screen may blank, system never suspends
gsettings set org.gnome.settings-daemon.plugins.power power-button-action 'nothing'      # guests can't shut it down with a tap
gsettings set org.gnome.desktop.a11y.applications screen-keyboard-enabled true           # on-screen keyboard for the Barliste search field
gsettings set org.gnome.desktop.notifications show-banners false                        # no popups over the kiosk
```

The waking tap only wakes — it can't accidentally book anything.

Portrait: rotate once in **Settings → Displays** as kiosk user; Wayland rotates touch coordinates automatically.

## 9. Auto-Updates + Monthly Reboot

Security patches install automatically; a controlled monthly reboot applies anything that needs a restart (kernel, libc) at a quiet hour instead of mid-service.

### 9.1 Enable unattended security upgrades

```bash
sudo apt install -y unattended-upgrades
# turn the periodic jobs on: refresh package lists daily + apply upgrades daily
cat <<'EOF' | sudo tee /etc/apt/apt.conf.d/20auto-upgrades
APT::Periodic::Update-Package-Lists "1";   # 1 = run daily
APT::Periodic::Unattended-Upgrade "1";     # 1 = apply upgrades daily
EOF
```

Disable unattended-upgrades' *own* reboot — we reboot on our schedule, not mid-shift:

```bash
sudo sed -i 's|^//\?\s*Unattended-Upgrade::Automatic-Reboot .*|Unattended-Upgrade::Automatic-Reboot "false";|' \
  /etc/apt/apt.conf.d/50unattended-upgrades
```

Verify it's active:

```bash
sudo systemctl status unattended-upgrades   # should be active/enabled
sudo unattended-upgrade --dry-run --debug    # shows what would be upgraded
```

### 9.2 Monthly maintenance reboot (systemd timer)

`/etc/systemd/system/monthly-reboot.service`:

```ini
[Unit]
Description=Monthly maintenance reboot (applies pending updates)

[Service]
Type=oneshot
ExecStart=/sbin/shutdown -r now
```

`/etc/systemd/system/monthly-reboot.timer`:

```ini
[Unit]
Description=Trigger monthly maintenance reboot

[Timer]
OnCalendar=*-*-01 04:30    # 1st of each month, 04:30 — after nightly backup+mirror
Persistent=true            # if the box was off at 04:30, run at next boot

[Install]
WantedBy=timers.target
```

Enable + verify:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now monthly-reboot.timer
sudo systemctl list-timers monthly-reboot.timer   # confirm next run date
```

The full quiet-hour sequence: **04:00** local backup → **04:15** NAS mirror → **04:30** reboot (1st of month), so the machine always reboots with a fresh, already-mirrored backup.

## 10. Chromium Kiosk — crash-proofed

```bash
sudo snap install chromium
```

Create `/home/kiosk/kiosk.sh` — copy-paste as one block:

```bash
cat > /home/kiosk/kiosk.sh <<'EOF'
#!/usr/bin/env bash
URL="http://localhost"

# Rewrite crash flags so Chromium never shows the "restore session?" bubble
PREFS="$HOME/snap/chromium/common/chromium/Default/Preferences"
if [ -f "$PREFS" ]; then
  sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/' "$PREFS"
  sed -i 's/"exited_cleanly":false/"exited_cleanly":true/' "$PREFS"
fi

exec chromium \
  --kiosk "$URL" \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-restore-session-state \
  --disable-pinch \
  --overscroll-history-navigation=0 \
  --touch-events=enabled \
  --check-for-update-interval=31536000
EOF
chmod +x /home/kiosk/kiosk.sh
chown kiosk:kiosk /home/kiosk/kiosk.sh
```

| Flag | Purpose |
|---|---|
| `--kiosk` | Fullscreen, no address bar, no tabs, no menus |
| `--noerrdialogs` | No error dialogs blocking the screen |
| `--disable-infobars` | No "Chromium is being controlled" bars |
| `--disable-session-crashed-bubble` | Belt-and-braces against the restore bubble |
| `--disable-restore-session-state` | Always start fresh on the URL |
| `--disable-pinch` | No pinch-zoom breaking the layout |
| `--overscroll-history-navigation=0` | Swipes must not trigger back/forward |
| `--touch-events=enabled` | Proper touch handling |
| `--check-for-update-interval=31536000` | No update prompts (snap updates anyway) |

`/home/kiosk/.config/systemd/user/kiosk.service`:

```ini
[Unit]
Description=Chromium Kiosk (Barsystem)
PartOf=graphical-session.target          # bind lifecycle to the GUI session
After=graphical-session.target

[Service]
# wait until the app answers — Chromium must not race Docker at boot
ExecStartPre=/bin/sh -c 'until curl -sf -o /dev/null http://localhost; do sleep 2; done'
ExecStart=/home/kiosk/kiosk.sh
Restart=always                           # any crash: back within seconds
RestartSec=3

[Install]
WantedBy=graphical-session.target
```

Enable:

```bash
sudo -u kiosk mkdir -p /home/kiosk/.config/systemd/user
# place the file, then:
sudo loginctl enable-linger kiosk        # user services allowed at boot
sudo -u kiosk XDG_RUNTIME_DIR=/run/user/$(id -u kiosk) \
  systemctl --user enable kiosk.service
```

### Crash-proofing summary

| Failure | Handled by |
|---|---|
| Chromium crashes | `Restart=always`, 3 s |
| "Restore pages?" bubble | Prefs rewrite + flags |
| App container dies | `restart: unless-stopped` |
| App not up yet at boot | `ExecStartPre` wait-loop |
| Power cut | Docker + autologin + service chain, unattended |
| Network down / off-grid | Everything is `localhost` |

## 11. Reboot + Verification

```bash
sudo reboot
```

- [ ] Boots straight into Barliste, fullscreen, portrait, touch aligned
- [ ] Search field tap → on-screen keyboard appears
- [ ] Screen blanks after 5 min; one tap wakes it, no lock screen
- [ ] `ssh admin@barsystem.local` works
- [ ] `nmap barsystem.local` shows **only 22 and 80**
- [ ] Cable pulled → kiosk keeps working (off-grid)
- [ ] `sudo pkill chromium` via SSH → kiosk back within ~5 s
- [ ] `docker compose restart` in `/opt/barsystem` → page recovers
- [ ] `systemctl list-timers monthly-reboot.timer` shows a valid next run

---

## Appendix A: Two-Stage Backup (corruption-safe)

Bookings live on the terminal's SSD, so they need protecting against both **SSD failure** and **data corruption**. The design is deliberately defensive:

- **Dated files, never overwritten** — a new dump can't clobber an older good one.
- **Integrity-checked before it's trusted** — a truncated or corrupt dump is deleted on the spot, so it never enters the backup set or reaches the NAS.
- **Append-only mirror to the NAS** — the terminal can *add* to the NAS but never *delete* from it, so a corrupted or wiped SSD can't destroy the off-box history.
- **Two stages** — the local copy is the fast restore; the NAS copy is the disaster copy.

Order matters: **replicate locally first, verify, then mirror the verified result to the NAS.**

### A.1 Stage 1 — local replication + integrity check

`/opt/barsystem/backup.sh`:

```bash
cat > /opt/barsystem/backup.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/opt/barsystem/backups"
STAMP="$(date +%F_%H%M)"
FILE="$BACKUP_DIR/barsystem_${STAMP}.sql.gz"
mkdir -p "$BACKUP_DIR"

# Read the DB user/name from the app's .env (no hardcoded credentials)
set -a; . /opt/barsystem/.env; set +a

# 1. Dump to a NEW dated file — existing backups are never touched
docker exec barsystem-db pg_dump -U "$DATABASE_USERNAME" "$DATABASE_NAME" | gzip > "$FILE"

# 2. Gzip integrity: catches a truncated/partial write
if ! gzip -t "$FILE"; then
  echo "$(date) CORRUPT (gzip) — discarding $FILE" >&2
  rm -f "$FILE"; exit 1
fi

# 3. Completeness: a full pg_dump ends with this marker line
if ! zcat "$FILE" | tail -n 5 | grep -q "PostgreSQL database dump complete"; then
  echo "$(date) INCOMPLETE dump — discarding $FILE" >&2
  rm -f "$FILE"; exit 1
fi

# 4. Local retention: keep 30 days of verified dumps
find "$BACKUP_DIR" -name 'barsystem_*.sql.gz' -mtime +30 -delete
echo "$(date) OK $FILE"
EOF
chmod +x /opt/barsystem/backup.sh
```

Only a dump that passes both checks stays on disk. A bad dump is removed and the script exits non-zero (visible in the log), so corruption never silently propagates.

### A.2 Stage 2 — append-only mirror to the Synology

Pick **one** of the two directions below. Both move the same verified dumps to the NAS append-only; they differ only in **which machine holds the credentials and initiates the transfer**.

| | **Option A — Terminal pushes** | **Option B — NAS pulls** |
|---|---|---|
| Who initiates | The kiosk (cron) | The NAS (DSM Task Scheduler) |
| Who holds a key | Kiosk holds a key to the NAS | NAS holds a key to the kiosk |
| If the kiosk is stolen/tampered | Attacker has a credential *into* the NAS | Attacker has nothing — no NAS credential on the box |
| If the NAS is down | Kiosk skips, retries next day | NAS just runs when it's back |
| Best when | NAS SSH is locked down; simplest to reason about | **Kiosk is physically exposed in a public bar** (recommended) |

> For a bar terminal sitting in a public space, **Option B is the safer default** — the exposed device carries no secret that reaches the NAS. Choose Option A only if you'd rather not enable inbound SSH pulls against the kiosk from the NAS.

---

#### Option A — Terminal pushes to the NAS

One-time: create an SSH key on the terminal, and enable SSH on the NAS (DSM → Terminal & SNMP → Enable SSH).

```bash
ssh-keygen -t ed25519 -f /home/admin/.ssh/nas -N ""
ssh-copy-id -i /home/admin/.ssh/nas.pub admin@synology.local   # NAS account
```

`/opt/barsystem/mirror-to-nas.sh`:

```bash
cat > /opt/barsystem/mirror-to-nas.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

SRC="/opt/barsystem/backups/"
NAS_USER="admin"
NAS_HOST="synology.local"
NAS_DEST="/volume1/barsystem-backups/"
KEY="/home/admin/.ssh/nas"

# Off-grid safe: if the NAS isn't reachable, skip quietly and try again tomorrow
if ! ping -c1 -W2 "$NAS_HOST" >/dev/null 2>&1; then
  echo "$(date) NAS offline — mirror skipped"; exit 0
fi

# Append-only push:
#   --ignore-existing : a file already on the NAS is NEVER re-sent or overwritten
#   (no --delete)     : files on the NAS are NEVER removed from here
# => a corrupt or empty local dir cannot damage the NAS history.
rsync -av --ignore-existing \
  --include='barsystem_*.sql.gz' --exclude='*' \
  -e "ssh -i $KEY" \
  "$SRC" "$NAS_USER@$NAS_HOST:$NAS_DEST"
echo "$(date) mirror complete"
EOF
chmod +x /opt/barsystem/mirror-to-nas.sh
```

Schedule it on the **terminal** (cron, user `admin`) — see A.3, Option A.

---

#### Option B — NAS pulls from the terminal (recommended for exposed kiosks)

The credential lives on the NAS; the kiosk only needs its SSH server (already enabled in §3). Harden the pull by restricting the key to a read-only rsync command on the terminal.

One-time, on the **NAS** (DSM → Control Panel → Terminal & SNMP → Enable SSH, then open an SSH session to the NAS):

```bash
# On the NAS: make a key for the pull job
mkdir -p /volume1/barsystem-backups
ssh-keygen -t ed25519 -f /root/.ssh/kiosk_pull -N ""
cat /root/.ssh/kiosk_pull.pub    # copy this line
```

On the **terminal**, add that public key to the `admin` account but lock it to a single read-only command, so a stolen NAS key can only *read* backups — never log in or write:

```bash
# /home/admin/.ssh/authorized_keys  — prepend the restriction, one line:
command="rsync --server --sender -vlogDtpre.iLsfxC . /opt/barsystem/backups/",restrict ssh-ed25519 AAAA...NAS_KEY... kiosk-pull
```

The `command=…,restrict` prefix means that key can do nothing but serve `/opt/barsystem/backups/` to a pulling rsync — no shell, no port forwarding, no writes.

On the **NAS**, create the pull script `/volume1/barsystem-backups/pull-from-kiosk.sh`:

```bash
#!/bin/bash
set -euo pipefail

KIOSK_USER="admin"
KIOSK_HOST="barsystem.local"
KIOSK_SRC="/opt/barsystem/backups/"
DEST="/volume1/barsystem-backups/"
KEY="/root/.ssh/kiosk_pull"

# If the kiosk is off/off-grid, skip quietly
if ! ping -c1 -W2 "$KIOSK_HOST" >/dev/null 2>&1; then
  echo "$(date) kiosk offline — pull skipped"; exit 0
fi

# Append-only pull:
#   --ignore-existing : never overwrite a dump already on the NAS
#   (no --delete)     : never remove NAS history because the kiosk lost/corrupted a file
rsync -av --ignore-existing \
  --include='barsystem_*.sql.gz' --exclude='*' \
  -e "ssh -i $KEY -o StrictHostKeyChecking=accept-new" \
  "$KIOSK_USER@$KIOSK_HOST:$KIOSK_SRC" "$DEST"
echo "$(date) pull complete"
```

```bash
chmod +x /volume1/barsystem-backups/pull-from-kiosk.sh
```

Schedule it on the **NAS** — see A.3, Option B.

---

Either way the transfer is **write-once and never deletes**, so the NAS accumulates every verified dump the terminal ever produced. Prune it on the **NAS side** (DSM Task Scheduler, e.g. keep 12 months) so retention decisions live where the data is safe.

### A.3 Schedule the backup + your chosen mirror

The nightly local dump always runs on the **terminal** (cron, user `admin`):

```bash
crontab -e
```

```cron
0 4 * * *  /opt/barsystem/backup.sh >> /opt/barsystem/backups/backup.log 2>&1   # 04:00 local dump + verify
```

Then add the mirror on whichever side you chose:

**Option A — on the terminal** (same crontab):

```cron
15 4 * * *  /opt/barsystem/mirror-to-nas.sh >> /opt/barsystem/backups/mirror.log 2>&1   # 04:15 push to NAS
```

**Option B — on the NAS** (DSM → Control Panel → Task Scheduler → Create → Scheduled Task → User-defined script, run as `root`, daily 04:15):

```
bash /volume1/barsystem-backups/pull-from-kiosk.sh >> /volume1/barsystem-backups/pull.log 2>&1
```

The monthly reboot at 04:30 (§9.2) lands after the 04:00 dump and 04:15 mirror, so every reboot follows a fresh, mirrored backup.

### A.4 Restore (know this before you need it)

```bash
# pick a verified dump, newest last
ls -1 /opt/barsystem/backups/barsystem_*.sql.gz

# restore into the running DB container (DB user/name come from .env)
set -a; . /opt/barsystem/.env; set +a
zcat /opt/barsystem/backups/barsystem_2026-07-20_0400.sql.gz \
  | docker exec -i barsystem-db psql -U "$DATABASE_USERNAME" "$DATABASE_NAME"
```

If the SSD itself is gone: rebuild the terminal (§1–§11), copy a dump back from the NAS (`scp admin@synology.local:/volume1/barsystem-backups/<file> .`), then run the restore lines above.
