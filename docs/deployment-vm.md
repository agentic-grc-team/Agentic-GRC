# Beta deployment on the university VMs

The Beta runs on two virtual machines reached through the bastion `pai.udea.edu.co:22666`.
Login stays on Supabase Auth. The files referenced below are in [`deploy/vm/`](../deploy/vm/).
Day-to-day operations (logs, restarts, troubleshooting, backups and recovery) are in
[`runbook-vm.md`](runbook-vm.md).

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

1. `sudo apt install -y nginx nodejs npm`. Use `DB_HOST=db-agentic-grc.gita.lan`: the internal DNS
   resolves it from the app VM (`getent hosts db-agentic-grc.gita.lan`), so no `/etc/hosts` entry is needed.
2. Ollama: copy the Vulkan build to `/opt/ollama` and the models to `/var/lib/ollama/models`,
   create the `ollama` user, install [`systemd/ollama.service`](../deploy/vm/systemd/ollama.service)
   and `sudo systemctl enable --now ollama`.
3. Backend:
   ```bash
   sudo useradd --system --home-dir /var/lib/agentic-grc --create-home --shell /usr/sbin/nologin agrc
   sudo git clone https://github.com/agentic-grc-team/Agentic-GRC.git /opt/agentic-grc
   sudo chown -R agrc:agrc /opt/agentic-grc
   # The system Python is 3.14; use 3.13 (as in CI) through uv, installed where agrc can read it.
   sudo env UV_PYTHON_INSTALL_DIR=/opt/uv-python uv python install 3.13
   sudo env UV_PYTHON_INSTALL_DIR=/opt/uv-python uv venv --seed --python 3.13 --python-preference only-managed /opt/agentic-grc/.venv
   sudo uv pip install --python /opt/agentic-grc/.venv/bin/python -r /opt/agentic-grc/backend/requirements.txt
   sudo chown -R agrc:agrc /opt/agentic-grc
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
   sudo -u agrc env VITE_BASE_PATH=/agentic-grc/ VITE_SUPABASE_URL=https://gita.udea.edu.co/agentic-grc/supabase \
     VITE_SUPABASE_PUBLISHABLE_KEY=<...> VITE_SHOW_DEMO_REPORT=false npm run build
   grep -o 'src="[^"]*"' dist/index.html   # must start with /agentic-grc/assets/
   ```
   The public URL is `https://gita.udea.edu.co/agentic-grc/`. The university proxy strips the
   prefix, so nginx serves `dist/` at `/`, while the browser keeps using `/agentic-grc/...`.
   `VITE_SUPABASE_URL` points to the `/supabase/` location of our nginx, not to `*.supabase.co`:
   the university proxy adds `Content-Security-Policy: connect-src 'self' https://gita.udea.edu.co`,
   which blocks direct calls to Supabase ("Failed to fetch" on sign-in).
   Do not set `VITE_API_BASE_URL`: by default the API base follows the base path
   (`/agentic-grc/api/v1`). Supabase Auth must allow
   `https://gita.udea.edu.co/agentic-grc/auth/callback` in its Redirect URLs.
8. nginx: install [`nginx/agentic-grc.conf`](../deploy/vm/nginx/agentic-grc.conf) in
   `/etc/nginx/sites-available/`, link it in `sites-enabled/`, remove the `default` site, then
   `sudo nginx -t && sudo systemctl reload nginx`.

## Accounts and memberships (no SMTP)

Outbound SMTP is blocked, so **Send invitation** fails. Users who already exist in Supabase Auth
(and in the local `auth.users`, step 1.5) are given access with SQL on the database VM:

```sql
-- Profiles for every confirmed user (also created automatically at first sign-in).
INSERT INTO public.users (id, email)
SELECT id, lower(trim(email)) FROM auth.users WHERE email_confirmed_at IS NOT NULL
ON CONFLICT (id) DO NOTHING;
-- Platform administrators can create organizations (bootstrap-admin only works for the first one).
UPDATE public.users SET is_platform_admin = true WHERE lower(email) = '<email>';
-- After creating the organization in the app: add members (the id has no server default).
INSERT INTO public.organization_memberships (id, organization_id, user_id, role, status)
SELECT gen_random_uuid(), o.id, u.id, '<consultant|representative|administrator>', 'active'
FROM public.organizations o, public.users u
WHERE o.name = '<organization>' AND lower(u.email) = '<email>';
```

There is no member list in the UI yet; check memberships with SQL or by signing in as that user.

## 3. Checks

```bash
systemctl is-active ollama agentic-grc-api nginx      # three "active"
curl -s http://127.0.0.1/api/v1/health                 # through nginx
/opt/ollama/bin/ollama ps                              # llama3.1:8b, 100% GPU, UNTIL Forever
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

The installed nginx site and systemd units are copies, so a `git pull` does not change them. When a
merge touches `deploy/vm/`, apply it on the VM (review the diff first: `git diff HEAD@{1} -- deploy/vm`):

```bash
# nginx (fill <SUPABASE_PROJECT_REF> again in the installed copy)
sudo cp deploy/vm/nginx/agentic-grc.conf /etc/nginx/sites-available/agentic-grc
sudo sed -i 's/<SUPABASE_PROJECT_REF>/<your-project-ref>/g' /etc/nginx/sites-available/agentic-grc
sudo nginx -t && sudo systemctl reload nginx

# systemd units (app VM)
sudo cp deploy/vm/systemd/ollama.service deploy/vm/systemd/agentic-grc-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart ollama agentic-grc-api      # the API reloads the model (~45 s)

# new variables in deploy/vm/backend.env.example: add them to /etc/agentic-grc/backend.env by hand
diff <(grep -oE '^[A-Z_]+=' deploy/vm/backend.env.example | sort) <(sudo grep -oE '^[A-Z_]+=' /etc/agentic-grc/backend.env | sort)
```

Then run the checks in section 3 and sign in through the public URL.

## Notes

- **Benchmarks on the VM** (`scripts/benchmark_models.py`) load the model with a 30 min keep-alive.
  Afterwards run `sudo systemctl restart agentic-grc-api` so the warm-up sets it back to forever;
  otherwise the first interview turn after 30 min reloads the model and times out (keyword fallback).
- After a reboot, the API waits for Ollama and the warm-up loads the model cold (~41 s). The API
  answers once that finishes (`journalctl -u agentic-grc-api -b | grep model`).
