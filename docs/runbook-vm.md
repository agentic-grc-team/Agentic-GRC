# Beta operations runbook (university VMs)

How to run the Beta from day to day: reach the VMs, change the configuration, start and stop the
services, read the logs, restart them and recover from failures. The first install is in
[`deployment-vm.md`](deployment-vm.md). File paths and service names below come from that guide
and from [`deploy/vm/`](../deploy/vm/).

> **Secrets stay out of this repo.** Never paste passwords, keys, tokens, connection strings or
> `.env` content into this file, an issue, a PR, a chat or a commit. Ask the team lead for VM
> access and for the values in `/etc/agentic-grc/backend.env`.

## At a glance

| VM | Services (systemd) | Logs | Data |
|---|---|---|---|
| `agentic-grc` (app) | `nginx`, `agentic-grc-api`, `ollama` | `journalctl -u <service>`, `/var/log/nginx/` | Evidence files in `/var/lib/agentic-grc/uploaded_evidence` |
| `db-agentic-grc` (database) | `postgresql`, `agentic-grc-backup.timer` | `/var/log/postgresql/`, `journalctl -u agentic-grc-backup` | Database `agentic_grc`, dumps in `/var/backups/agentic-grc` |

Public URL: `https://gita.udea.edu.co/agentic-grc/`. Request path:
university proxy → nginx `:80` → API `127.0.0.1:8000` → Ollama `127.0.0.1:11434` and PostgreSQL
on `db-agentic-grc:5432`.

## 1. Access

Both VMs are reached through the bastion `pai.udea.edu.co:22666`. Put this in your own
`~/.ssh/config`, using the account the team lead gave you:

```sshconfig
Host agrc-bastion
    HostName pai.udea.edu.co
    Port 22666
    User <your-user>

Host agentic-grc db-agentic-grc
    User <your-user>
    ProxyJump agrc-bastion
```

Then `ssh agentic-grc` or `ssh db-agentic-grc`. Use SSH keys, not passwords saved in files.

## 2. Configuration

The backend reads only `/etc/agentic-grc/backend.env` (`root:agrc`, mode `640`). The template, with
every variable and its Beta value, is [`deploy/vm/backend.env.example`](../deploy/vm/backend.env.example).

```bash
sudo -e /etc/agentic-grc/backend.env           # edit
sudo stat -c '%U:%G %a' /etc/agentic-grc/backend.env   # must print root:agrc 640
sudo systemctl restart agentic-grc-api         # the API reads the file only at startup
```

The frontend settings (`VITE_*`) are compiled into `frontend/dist` at build time. To change them,
rebuild as in step 7 of [`deployment-vm.md`](deployment-vm.md); restarting a service does not
pick them up.

Settings you are most likely to change:

| Need | Variable | Note |
|---|---|---|
| Interview turns fall back to keywords too often | `AGRC_LLM_TIMEOUT_S` | Keep it under the 120 s nginx/proxy timeout, counting two calls per turn |
| Model unloads between interviews | `AGRC_LLM_KEEP_ALIVE` | Also `OLLAMA_KEEP_ALIVE` in `ollama.service` |
| Database password rotated | `DB_PASSWORD` | Change it in PostgreSQL first (`sudo -u postgres psql -c '\password agentic_grc'`, which prompts and keeps it out of shell history), then here |

After changing a systemd unit file: `sudo systemctl daemon-reload` and then restart that service.

## 3. Start, stop and status

Start order matters: database first, then the model, then the API, then nginx. systemd already
starts `agentic-grc-api` after `ollama` on the app VM, but it does not wait for the database VM.

```bash
# database VM
sudo systemctl start postgresql
# app VM
sudo systemctl start ollama agentic-grc-api nginx

# status
systemctl is-active ollama agentic-grc-api nginx       # app VM: three "active"
systemctl is-active postgresql                         # database VM
systemctl list-timers agentic-grc-backup.timer         # database VM: next backup run

# stop (the reverse order)
sudo systemctl stop nginx agentic-grc-api ollama       # app VM
sudo systemctl stop postgresql                         # database VM
```

All services are enabled, so they come back on their own after a reboot.

## 4. Health checks

Run these on the app VM after any start, restart or redeploy:

```bash
curl -s http://127.0.0.1/api/v1/health                  # {"status":"ok"} through nginx
curl -s http://127.0.0.1:8000/api/v1/health             # same, straight to the API
curl -s http://127.0.0.1:11434/api/ps                   # llama3.1:8b listed = model loaded
timeout 3 bash -c '</dev/tcp/db-agentic-grc/5432' && echo "database port open"
```

The health endpoint does not touch the database or the model. To confirm the whole chain, log in
at the public URL and open an assessment. To load the model by hand (for example, before a demo):

```bash
cd /opt/agentic-grc/backend
sudo -u agrc env AGRC_ENV_FILE=/etc/agentic-grc/backend.env ../.venv/bin/python -m app.cli warm-up-model
```

## 5. Logs

```bash
# app VM
sudo journalctl -u agentic-grc-api -f                   # API, live
sudo journalctl -u agentic-grc-api --since "1 hour ago"
sudo journalctl -u ollama -n 200                        # model server
sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log

# database VM
sudo tail -n 200 /var/log/postgresql/postgresql-*-main.log
sudo journalctl -u agentic-grc-backup -n 50             # last backup runs
sudo -u postgres ls -lh /var/backups/agentic-grc       # backups present and recent (the folder is postgres-only)
```

Add `-b` to `journalctl` to see only the current boot. Logs can contain interview content; do not
copy them outside the VMs, and remove assessment text before you quote a log in an issue.

## 6. Restart

```bash
sudo systemctl restart agentic-grc-api      # after a config change or redeploy
sudo systemctl restart ollama               # model hung or out of GPU memory; the API restart reloads it
sudo nginx -t && sudo systemctl reload nginx   # after an nginx config change (no downtime)
sudo systemctl restart postgresql           # database VM; the API reconnects on the next request
```

After a full VM reboot, run the checks in section 4. Wait for the model warm-up: the first
interview turn after a reboot is slower.

## 7. Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| Public URL does not answer | nginx down, or the university proxy cannot reach the app VM | `systemctl status nginx`; `curl http://127.0.0.1/` on the VM. If it works locally, report it to the proxy admins |
| `502 Bad Gateway` | API not running | `journalctl -u agentic-grc-api -n 100`, fix the cause, restart the API |
| `504 Gateway Timeout` on an interview turn | Model slower than the 120 s proxy timeout | `curl .../api/ps` to check the model is loaded; run `warm-up-model`; check `journalctl -u ollama` |
| Turns answer but follow-ups look generic | LLM timeout: the agent used the keyword fallback | Check `/api/ps` and the Ollama log; adjust `AGRC_LLM_TIMEOUT_S` (section 2) |
| API restarts in a loop | Bad value in `backend.env`, or the database is unreachable | Read the first error in `journalctl -u agentic-grc-api -b`; check the database port (section 4) |
| Database errors in the API log | PostgreSQL down, `pg_hba.conf` or SSL rejecting the app VM | `systemctl status postgresql` and the PostgreSQL log on the database VM |
| Login works in Supabase but the app refuses the user | User missing from `auth.users` on the database VM | Insert the user as in step 5 of the database setup in [`deployment-vm.md`](deployment-vm.md) |
| Sign-in stays on "Signing in…", nginx `error.log` shows `upstream timed out … while connecting to upstream` with an `upstream` address starting with `64:ff9b::` | nginx resolved Supabase once, at start, to a NAT64 address that no longer works | `sudo systemctl restart nginx` so it resolves the name again. `curl -sS -o /dev/null -w '%{http_code}\n' https://<ref>.supabase.co/auth/v1/health` from the VM should answer `401` (no key) quickly |
| Sign-in fails and `access.log` shows `POST /supabase/auth/v1/token…` with `401` | Frontend built with a wrong publishable key (a wrong password answers `400`) | Rebuild the frontend as in step 7 of [`deployment-vm.md`](deployment-vm.md), taking the key from `backend.env` |
| Blank page or missing assets | Frontend built without `VITE_BASE_PATH=/agentic-grc/` | Rebuild (step 7) and run the `grep` check from the guide |
| Disk full | Old dumps, logs or evidence | `df -h`; `sudo journalctl --vacuum-time=14d`; dumps older than 14 days are already deleted |

## 8. Recovery

### Roll back a bad redeploy

```bash
cd /opt/agentic-grc
sudo -u agrc git log --oneline -10            # find the last good commit
sudo -u agrc git checkout <good-commit>
sudo -u agrc .venv/bin/pip install -r backend/requirements.txt
# rebuild the frontend (step 7 of deployment-vm.md), then:
sudo systemctl restart agentic-grc-api
```

If the bad release ran a database migration, rolling back the code is not enough: restore the
database from the dump taken before the release (next section). Do not run `alembic downgrade` on
the Beta unless you have checked that the migration's downgrade keeps the data. To return to the
normal state later: `sudo -u agrc git checkout main && sudo -u agrc git pull`.

### Restore the database from a backup

The nightly dump covers the whole `agentic_grc` database, including the `auth.users` stand-in and
the LangGraph checkpoints in `agentic_grc_private`. Take a fresh dump before restoring, so the
restore can be undone.

```bash
# app VM: stop writes
sudo systemctl stop agentic-grc-api

# database VM
sudo -u postgres /usr/local/bin/agentic-grc-backup            # safety dump of the current state
sudo -u postgres ls -lt /var/backups/agentic-grc | head      # choose the dump to restore
sudo -u postgres pg_restore --clean --if-exists -d agentic_grc /var/backups/agentic-grc/agentic_grc-<timestamp>.dump

# app VM
sudo systemctl start agentic-grc-api
```

Then run the checks in section 4 and log in. Interviews resume from the restored checkpoints.

### Verify a backup (restore check)

A dump is only known to be good once it has been restored. This check restores the newest dump
into a separate database, `agentic_grc_restore_check`, compares it with the live database and
removes it. The live `agentic_grc` is only read, and the API keeps running. Copy
[`postgres/restore-check.sql`](../deploy/vm/postgres/restore-check.sql) to `/tmp` on the database
VM first, like the other `deploy/vm/` files.

```bash
# database VM
systemctl list-timers agentic-grc-backup.timer --no-pager    # last and next run
sudo journalctl -u agentic-grc-backup -n 10 --no-pager        # the last runs succeeded
sudo -u postgres ls -l --time-style=+%Y-%m-%dT%H:%M:%S%z /var/backups/agentic-grc
DUMP=$(sudo -u postgres sh -c 'ls -t /var/backups/agentic-grc/agentic_grc-*.dump | head -1')
sudo -u postgres pg_restore --list "$DUMP" | sed -n '2,12p'   # "Archive created at" is the backup time
df -h /var/lib/postgresql                                     # room for a second copy of the database

sudo -u postgres dropdb --if-exists agentic_grc_restore_check   # leftover from an interrupted check
sudo -u postgres createdb -O agentic_grc -E UTF8 -T template0 agentic_grc_restore_check
sudo -u postgres pg_restore --exit-on-error --single-transaction -d agentic_grc_restore_check "$DUMP"
for db in agentic_grc agentic_grc_restore_check; do
  echo "== $db"; sudo -u postgres psql -d "$db" -XAt -F ' | ' -f /tmp/restore-check.sql
done
sudo -u postgres dropdb agentic_grc_restore_check
```

The check passes when `pg_restore` ends without an error and both databases show the same Alembic
version, the same table and trigger counts, and the same rows. The live database may have more
rows than the restored one, but only rows created after the backup time (compare the "newest"
lines). The restored database is a full copy of the Beta data: drop it as soon as the comparison
is done.

`pg_dump` does not keep database-level permissions, so a database restored from a dump accepts
connections from every role until the grants are applied again (see [A VM is lost](#a-vm-is-lost)).
Restoring over the live database (previous section) keeps them.

| Date | Dump checked (`Archive created at`) | Result | Notes |
|---|---|---|---|
| 2026-11-21 | `agentic_grc-20261121T073023Z.dump`, created 2026-11-21 07:30:23 UTC (304 KB, PostgreSQL 18.6) | Passed | Restored on `db-agentic-grc` without errors. Same Alembic version (`20261116_0011`), tables, 8 triggers and row counts as the live database (10 assessments, 103 interview turns, 201 checkpoints; newest data 2026-11-18). Nightly runs succeeded every day from 18 to 21 Nov. The manual `pre-*.dump` files are outside the 14-day cleanup and stay until removed by hand. |
| 2026-11-21 | Local rehearsal on PostgreSQL 18.7 with migrations up to `20261116_0011` and demo data | Passed | Same counts and triggers; the app role could read the copy, and the append-only triggers still rejected `UPDATE`. |

### Evidence files

Uploaded evidence is stored on the app VM in `/var/lib/agentic-grc/uploaded_evidence`, not in the
database, so **the nightly dump does not include it**. Database rows that point to evidence are
restored, but the files are not. Before maintenance, or after a demo with new uploads, copy the
folder off the VM to storage approved for this data:

```bash
sudo tar -czf /tmp/evidence-$(date -u +%Y%m%d).tar.gz -C /var/lib/agentic-grc uploaded_evidence
# restore: stop the API, extract into /var/lib/agentic-grc, then:
sudo chown -R agrc:agrc /var/lib/agentic-grc/uploaded_evidence
```

Delete the archive from `/tmp` once it has been copied.

### A VM is lost

1. Rebuild it from [`deployment-vm.md`](deployment-vm.md): section 1 for the database VM,
   section 2 for the app VM.
2. Database VM: create the role and the empty database (steps 1 to 3), restore the latest dump
   with `sudo -u postgres pg_restore --exit-on-error -d agentic_grc <dump>` instead of steps 4 and
   5, then apply `auth-users-grants.sql` (step 4): the dump does not include the database-level
   grants. The dumps live on the database VM itself, so if that VM is lost they are lost too unless
   a copy was kept elsewhere.
3. App VM: write `backend.env` again from the template and the values the team lead holds. Restore
   the evidence archive if you have one.
4. Run the checks in section 4.
