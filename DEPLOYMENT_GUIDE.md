# Deployment Guide

Last updated: 2026-05-18
Owner: Federation Platform Team
Review cadence: Every major infrastructure change

This guide walks through deploying the Sports Federation Management System
for the first time on a clean server. For upgrade instructions, see
[RELEASE_RUNBOOK.md](RELEASE_RUNBOOK.md).

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Docker Engine ≥ 24 | `docker --version` |
| Docker Compose plugin ≥ 2.20 | `docker compose version` |
| Git | For cloning the repository |
| 4 GB RAM (minimum) | 8 GB recommended for production |
| 20 GB disk | For database, filestore, and backups |

---

## 1. Docker Compose Stack Overview

The stack is defined in `docker-compose.yaml` at the repository root:

| Service | Image | Purpose |
|---|---|---|
| `db` | `postgres:18` | PostgreSQL database |
| `odoo` | `odoo:19` | Odoo application server |
| `mcp_odoo` | `mcp/odoo:latest` (profile: `tools`) | MCP server — started on demand only |

Default exposed ports:

| Port | Service |
|---|---|
| `10019` | Odoo HTTP (maps to container port `8069`) |
| `20019` | Odoo long-polling / gevent (maps to `8072`) |

---

## 2. Configuration Files

### `config/odoo.conf`

```ini
[options]
db_host = db
db_port = 5432
db_user = odoo
db_password = <CHANGE_ME>

list_db = True
dbfilter = .*

admin_passwd = <CHANGE_ME>

data_dir = /var/lib/odoo
addons_path = /mnt/extra-addons
```

**Required changes before first start:**

- `db_password` — set to the value of `POSTGRES_PASSWORD` in `docker-compose.yaml`
- `admin_passwd` — the master password for the `/web/database/manager` interface;
  use a strong random value in production

**Optional additions for production:**

```ini
workers = 4
max_cron_threads = 2
limit_memory_hard = 2684354560
limit_memory_soft = 2147483648
limit_request = 8192
limit_time_cpu = 60
limit_time_real = 120
proxy_mode = True
```

### Environment Variables in `docker-compose.yaml`

The `odoo` service accepts these environment variables. Add them under the
`environment:` block:

| Variable | Purpose | Example |
|---|---|---|
| `HOST` | PostgreSQL hostname | `db` |
| `USER` | PostgreSQL username | `odoo` |
| `PASSWORD` | PostgreSQL password | `<secret>` |
| `SMTP_SERVER` | Outbound mail server hostname | `smtp.example.com` |
| `SMTP_PORT` | SMTP port | `587` |
| `SMTP_SSL` | Use STARTTLS | `True` |
| `SMTP_USER` | SMTP login | `noreply@federation.example.com` |
| `SMTP_PASSWORD` | SMTP password | `<secret>` |

SMTP settings can also be configured post-install via
**Settings → Technical → Email → Outgoing Mail Servers**.

---

## 3. Initial Database Creation

```bash
# 1. Start only the database service
docker compose up -d db

# 2. Wait until PostgreSQL is ready
docker compose exec db pg_isready -U odoo

# 3. Start the Odoo service
docker compose up -d odoo

# 4. Check logs for startup errors
docker compose logs -f odoo
```

Open `http://localhost:10019/web/database/manager` in a browser. Create a new
database:

- **Database Name**: `odoo` (must match `ODOO_DB` in the MCP service if used)
- **Email**: admin email address
- **Password**: admin password
- **Language**: select your language
- **Country**: select your country
- **Demo Data**: leave **unchecked** for production

---

## 4. Installing Modules in Order

Install the federation modules in dependency order. Use the Odoo CLI
(recommended for production) or the Apps interface.

### Using the CLI

```bash
# Install the full federation stack
docker compose exec odoo odoo \
  -c /etc/odoo/odoo.conf \
  -d odoo \
  -i sports_federation_base,\
sports_federation_people,\
sports_federation_rules,\
sports_federation_tournament,\
sports_federation_competition_engine,\
sports_federation_venues,\
sports_federation_officiating,\
sports_federation_rosters,\
sports_federation_result_control,\
sports_federation_standings,\
sports_federation_compliance,\
sports_federation_discipline,\
sports_federation_governance,\
sports_federation_finance_bridge,\
sports_federation_notifications,\
sports_federation_portal,\
sports_federation_public_site,\
sports_federation_reporting,\
sports_federation_import_tools \
  --stop-after-init
```

**Do not install `sports_federation_demo` in production.** It creates synthetic
sample data.

### Recommended install order

Tier 1 (core) must be installed before tier 2 (domain), which must be installed
before tier 3 (portal/public):

```
Tier 1: sports_federation_base
Tier 2: sports_federation_people, sports_federation_rules,
        sports_federation_tournament, sports_federation_competition_engine,
        sports_federation_venues, sports_federation_officiating,
        sports_federation_rosters, sports_federation_result_control,
        sports_federation_standings, sports_federation_compliance,
        sports_federation_discipline, sports_federation_governance,
        sports_federation_finance_bridge, sports_federation_notifications
Tier 3: sports_federation_portal, sports_federation_public_site
Tier 4: sports_federation_reporting, sports_federation_import_tools
```

---

## 5. First Admin Setup Checklist

After the module install completes, perform these steps as the admin user:

1. **Set the federation name and logo**
   Settings → General Settings → Company → update name, logo, and timezone.

2. **Configure outbound mail**
   Settings → Technical → Email → Outgoing Mail Servers → create and test.

3. **Create the first season**
   Federation → Configuration → Seasons → New.

4. **Create security groups for staff**
   Settings → Users → Users → New → assign group
   `Sports Federation / Federation User` or `Sports Federation / Federation Manager`.

5. **Enable scheduled actions**
   Settings → Technical → Automation → Scheduled Actions → ensure these are active:
   - `Federation: Expire Player Licenses`
   - `Federation: GC Rate Limit Buckets`
   - `Federation: GC Staged Deliveries` (if import_tools is installed)

6. **Review ir.config_parameter defaults**
   Settings → Technical → Parameters → System Parameters.
   Rate-limit overrides use the pattern `sports_federation.rate_limit.<scope>.<field>`.

---

## 6. Post-Install Smoke Test

Verify the stack is healthy after installation:

```bash
# 1. Check Odoo service is running
docker compose ps

# 2. Open the public tournaments page (should return 200)
curl -sI http://localhost:10019/tournaments | head -5

# 3. Open the portal login page (should return 200)
curl -sI http://localhost:10019/web/login | head -5

# 4. Verify the JSON competition feed (should return JSON)
curl -s http://localhost:10019/competitions/api/json | python3 -m json.tool | head -20

# 5. Run the focused CI suites against the installed database (optional)
bash addons/ci/run_tests.sh --suite release_surfaces
```

A healthy stack shows:
- HTTP 200 on `/tournaments` and `/web/login`
- Valid JSON on `/competitions/api/json`
- All CI tests passing

---

## 7. MCP Server (On-Demand Tool)

The MCP server is not part of the default production stack. Start it only when
needed for Copilot or tooling access:

```bash
docker compose --profile tools run --rm mcp_odoo
```

It connects to the `odoo` service via `http://odoo:8069`. Configuration is in
the `mcp_odoo` service block in `docker-compose.yaml`.

---

## 8. Backup Configuration

The backup script stores compressed dumps under `./backups/`:

```bash
# Take a manual backup before any upgrade
bash scripts/upgrade_sports_federation.sh --db odoo --dry-run

# Or take a standalone backup
docker compose exec -T db pg_dump -U odoo -Fc odoo \
  > backups/$(date +%Y-%m-%d_%H%M%S)/odoo.dump
```

See [RELEASE_RUNBOOK.md](RELEASE_RUNBOOK.md) for the full backup and restore drill procedure.
