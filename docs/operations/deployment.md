# Deployment guide

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

This guide walks through deploying the Sports Federation platform for the
first time on a clean server. For upgrades, backups and rollback, see the
[release runbook](release-runbook.md).

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
**Settings > Technical > Email > Outgoing Mail Servers**.

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

## 4. Installing the platform

Install the platform through its single entry point with the Odoo CLI
(recommended for production) or the Apps interface.

### Using the CLI

```bash
# Install the complete production platform through its single entry point.
docker compose exec odoo odoo \
  -c /etc/odoo/odoo.conf \
  -d odoo \
  -i sports_federation_app \
  --stop-after-init
```

Do not install `sports_federation_demo` in production. It creates synthetic
sample data. Existing databases continue upgrading their installed domain
addons; installing `sports_federation_app` is additive and does not move data.

Odoo resolves the install order from the manifest dependencies. The
[module catalogue](../overview/modules.md#dependency-layers) shows the
resulting layers. Optional addons (`sports_federation_member_services`,
`sports_federation_accounting`) must be installed explicitly.

---

## 5. First Admin Setup Checklist

After the module install completes, perform these steps as the admin user:

1. **Set the federation name and logo**
   Settings > General Settings > Company > update name, logo, and timezone.

2. **Configure outbound mail**
   Settings > Technical > Email > Outgoing Mail Servers → create and test.

3. **Create the first season**
   **Federation > Competitions > Records > Seasons > New** (advanced menu).

4. **Create security groups for staff**
   Settings > Users > Users > New > assign group
   `Sports Federation / Federation User` or `Sports Federation / Federation Manager`.

5. **Enable scheduled actions**
   Settings > Technical > Automation > Scheduled Actions → ensure these are active:
   - `Federation: Expire Player Licenses`
   - `Federation: GC Rate Limit Buckets`
   - `Federation: GC Staged Deliveries` (if import_tools is installed)

6. **Review ir.config_parameter defaults**
   Settings > Technical > Parameters > System Parameters.
   Rate-limit overrides use the pattern `sports_federation.rate_limit.<scope>.<field>`.

---

## 6. Post-Install Smoke Test

Verify the stack is healthy after installation:

```bash
# 1. Check Odoo service is running
docker compose ps

# 2. Open the public competitions page (should return 200)
curl -sI http://localhost:10019/competitions | head -5

# 3. Open the portal login page (should return 200)
curl -sI http://localhost:10019/web/login | head -5

# 4. Verify the public competition feed (should return JSON)
curl -s http://localhost:10019/api/v1/competitions | python3 -m json.tool | head -20

# 5. Run the focused CI suites against the installed database (optional)
bash ci/run_tests.sh --suite release_surfaces
```

A healthy stack shows:
- HTTP 200 on `/competitions` and `/web/login`
- Valid JSON on `/api/v1/competitions`
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

See the [release runbook](release-runbook.md#backup-and-restore-drill) for the full backup and restore drill procedure.

## Trusted reverse proxies

Set `federation.trusted_proxy_networks` in `ir.config_parameter` to a comma-separated
CIDR allowlist containing only the immediate reverse proxies, for example
`10.24.0.0/16,192.0.2.10/32`. Forwarded client IP headers are ignored when the
TCP peer is outside this allowlist. Production must also run Odoo with
`proxy_mode = True` behind the listed proxy and must prevent direct public access
to the Odoo application port.
