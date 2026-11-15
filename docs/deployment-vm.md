# Beta deployment on the university VMs

The Beta runs on two virtual machines reached through the bastion `pai.udea.edu.co:22666`.
Login stays on Supabase Auth. The files referenced below are in [`deploy/vm/`](../deploy/vm/).

| VM | Runs |
|---|---|
| `agentic-grc` (app VM, Tesla M10) | nginx on port 80, the FastAPI backend and Ollama, all as systemd services |
| `db-agentic-grc` (database VM) | PostgreSQL 18 and the nightly `pg_dump` |

The university reverse proxy forwards the public URL to `agentic-grc:80`. It must allow
responses of at least 120 s (the same as nginx). An interview turn makes two model calls on the
M10: about 40 s per turn when the model is warm, and over 60 s when a call hits the timeout.

## Layout on the app VM

| What | Where |
|---|---|
| Repo | `/opt/agentic-grc` (owned by `agrc`) |
| Backend secrets | `/etc/agentic-grc/backend.env` (root:agrc, 640), from [`backend.env.example`](../deploy/vm/backend.env.example) |
| Backend data (uploaded evidence) | `/var/lib/agentic-grc` |
| Ollama binary and models | `/opt/ollama`, `/var/lib/ollama/models` |
| Service users | `agrc` (backend), `ollama` (model, in the `video` and `render` groups) |

## 1. Database VM

1. Install PostgreSQL. The VM's own DNS (`192.168.0.2`) does not resolve, so use the app VM's
   resolver for the install only:
   ```bash
   sudo resolvectl dns ens3 10.64.0.1
   sudo apt-get update && sudo apt-get install -y postgresql
   sudo resolvectl revert ens3
   ```
2. Copy [`postgres/agentic-grc.conf`](../deploy/vm/postgres/agentic-grc.conf) to
   `/etc/postgresql/<version>/main/conf.d/` and append
   [`postgres/pg_hba.line`](../deploy/vm/postgres/pg_hba.line) to `pg_hba.conf`, filling in both IPv6 addresses.
3. Create the role (with a strong password) and the database:
   ```bash
   sudo -u postgres createuser --login --pwprompt agentic_grc
   sudo -u postgres createdb -O agentic_grc -E UTF8 agentic_grc
   ```
4. Apply the `auth.users` stand-in and the grants:
   ```bash
   sudo -u postgres psql -d agentic_grc -f backend/tests/sql/supabase_auth_stub.sql
   sudo -u postgres psql -d agentic_grc -f deploy/vm/postgres/auth-users-grants.sql
   ```
5. Insert every Beta user into `auth.users`, with the `id` and `email` from Supabase
   (*Authentication → Users*). `public.users` has a foreign key to it.
6. Install the backup: [`scripts/agentic-grc-backup`](../deploy/vm/scripts/agentic-grc-backup) to
   `/usr/local/bin/`, the two `agentic-grc-backup.*` units to `/etc/systemd/system/`, then
   `sudo install -d -m 700 -o postgres -g postgres /var/backups/agentic-grc` and
   `sudo systemctl enable --now agentic-grc-backup.timer`.

## 2. App VM

1. `sudo apt install -y nginx python3-venv nodejs npm`, and add `db-agentic-grc` with its IPv6 to
   `/etc/hosts` (the name does not resolve from the app VM).
2. Ollama: copy the Vulkan build to `/opt/ollama` and the models to `/var/lib/ollama/models`,
   create the `ollama` user, install [`systemd/ollama.service`](../deploy/vm/systemd/ollama.service)
   and `sudo systemctl enable --now ollama`.
3. Backend:
   ```bash
   sudo useradd --system --home-dir /var/lib/agentic-grc --create-home --shell /usr/sbin/nologin agrc
   sudo git clone https://github.com/agentic-grc-team/Agentic-GRC.git /opt/agentic-grc
   sudo chown -R agrc:agrc /opt/agentic-grc
   sudo -u agrc python3 -m venv /opt/agentic-grc/.venv
   sudo -u agrc /opt/agentic-grc/.venv/bin/pip install -r /opt/agentic-grc/backend/requirements.txt
   ```
4. Write `/etc/agentic-grc/backend.env` from [`backend.env.example`](../deploy/vm/backend.env.example).
5. Schema, from `/opt/agentic-grc/backend`:
   ```bash
   sudo -u agrc env AGRC_ENV_FILE=/etc/agentic-grc/backend.env ../.venv/bin/alembic upgrade head
   sudo -u agrc env AGRC_ENV_FILE=/etc/agentic-grc/backend.env ../.venv/bin/python -m app.cli init-interview-checkpointer
   ```
6. Install [`systemd/agentic-grc-api.service`](../deploy/vm/systemd/agentic-grc-api.service) and
   `sudo systemctl enable --now agentic-grc-api`.
7. Frontend, from `/opt/agentic-grc/frontend`:
   ```bash
   sudo -u agrc npm ci
   sudo -u agrc env VITE_BASE_PATH=/agentic-grc/ VITE_SUPABASE_URL=<...> \
     VITE_SUPABASE_PUBLISHABLE_KEY=<...> VITE_SHOW_DEMO_REPORT=false npm run build
   grep -o 'src="[^"]*"' dist/index.html   # must start with /agentic-grc/assets/
   ```
   The public URL is `https://gita.udea.edu.co/agentic-grc/`. The university proxy strips the
   prefix, so nginx serves `dist/` at `/`, while the browser keeps using `/agentic-grc/...`.
   Do not set `VITE_API_BASE_URL`: by default the API base follows the base path
   (`/agentic-grc/api/v1`). Supabase Auth must allow
   `https://gita.udea.edu.co/agentic-grc/auth/callback` in its Redirect URLs.
8. nginx: install [`nginx/agentic-grc.conf`](../deploy/vm/nginx/agentic-grc.conf) in
   `/etc/nginx/sites-available/`, link it in `sites-enabled/`, remove the `default` site, then
   `sudo nginx -t && sudo systemctl reload nginx`.

## 3. Checks

```bash
systemctl is-active ollama agentic-grc-api nginx      # three "active"
curl -s http://127.0.0.1/api/v1/health                 # through nginx
curl -s http://127.0.0.1:11434/api/ps                  # llama3.1:8b loaded after the warm-up
sudo reboot                                            # then the first line again
```

## Redeploying after a merge to main

```bash
cd /opt/agentic-grc && sudo -u agrc git pull
sudo -u agrc .venv/bin/pip install -r backend/requirements.txt
cd backend && sudo -u agrc env AGRC_ENV_FILE=/etc/agentic-grc/backend.env ../.venv/bin/alembic upgrade head && cd ..
# rebuild the frontend as in step 7, then:
sudo systemctl restart agentic-grc-api
```
