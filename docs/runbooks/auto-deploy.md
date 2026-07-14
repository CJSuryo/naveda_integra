# Auto-deploy runbook (naveda)

Naveda auto-deploys on push to `main`, as of 2026-07-14. So does potum, on the
same box. This file describes what is *actually running* — it was rewritten after
the setup landed, because the version before it was a plan, and plans rot.

**Verify, don't trust this file.** Its predecessor claimed things about the box
that were false, which is how an hour disappeared. Every check below is a command.

---

## The shape of it

Render's "push → deploy" is just: *a push triggers a runner, the runner SSHes to
the box, the box runs a script.* That is all this is.

```
push to main
  → .github/workflows/deploy.yml
    → appleboy/ssh-action  (SSH to 5.223.77.16, host key pinned)
      → cd apps/projects/naveda_integra && ./deploy.sh
```

`deploy.sh` runs **on the box**: `flock` → `git pull --ff-only` → `docker compose
build` → `up -d` → `migrate` → `collectstatic` → healthcheck loop → `image prune`.

Images build **on the box**, not in CI. The runner ships no code; it only tells
the box to pull. That is why the box needs its own read credential (§ *Repo access*).

Migrations run at **deploy** time, not build time.

---

## The box

| | |
|---|---|
| SSH | `deploy@5.223.77.16` |
| Naveda | `~/apps/projects/naveda_integra`, published on `127.0.0.1:8080` |
| Potum | `~/apps/projects/potumsite`, published on `127.0.0.1:8081` |
| Edge | host Nginx (NOT in compose) reverse-proxies both, terminates TLS with a Cloudflare Origin CA cert |
| Specs | 2 vCPU / 4GB, shared by both stacks |

**SSH to the IP, never the hostname.** `navedafinance.com` is orange-clouded in
Cloudflare, which proxies HTTP(S) only. The hostname resolves to a Cloudflare edge
IP with nothing on :22 — SSH fails with `Network is unreachable`. Applies to your
laptop *and* to the `DEPLOY_HOST` secret.

**ufw has `22/tcp LIMIT IN`.** 6+ SSH connections in 30s and your IP is silently
DROPped (`Connection timed out`, self-expires in minutes). **Batch remote checks
into ONE `ssh` call.** A script that opens a connection per check will rate-limit
*you* halfway through and look exactly like a network outage.

**SSH is hardened** (`/etc/ssh/sshd_config.d/00-hardening.conf`): keys only, no
root login. Don't undo it. The `00-` prefix is load-bearing — `sshd_config.d/*` is
included at the TOP of `sshd_config`, and sshd honours the FIRST value it sees, so
a `99-` file would lose to cloud-init's `50-cloud-init.conf`. Editing
`/etc/ssh/sshd_config` directly does nothing.

Check *resolved* state, not files:
```bash
sudo sshd -T | grep -Ei "^(permitrootlogin|passwordauthentication)"
```

---

## Why the box and the repo must not drift

Before auto-deploy, the box ran config that existed **nowhere in git**: an
untracked `Dockerfile`, and local edits to `docker-compose.yml`. Auto-deploy would
have replaced both with the committed versions on the first push and taken
production down. Two of those edits are still the reason the committed values are
what they are:

- **`image: postgres:17`.** The `postgres_data` volume on the box is PG17. A PG16
  binary refuses to start against a PG17 data directory. Do not "helpfully" pin it
  back.
- **`ports: "127.0.0.1:8080:8000"`.** Nginx is the only edge. Publishing on
  `0.0.0.0:8080` serves the app over plain HTTP, bypassing Cloudflare and the cert.

Anything the box needs must be **committed**. `git status` on the box should be
clean; if it isn't, someone hand-edited production and the next `git pull
--ff-only` will fail (or silently keep the drift, if the file is untracked).

---

## deploy.sh, and the two steps you can't drop

**`flock /tmp/box-deploy.lock`.** Both stacks share a 4GB box, and GitHub's
`concurrency:` group is **per-repository** — it cannot see across repos, so it
cannot stop a naveda build from racing a potum one. Two simultaneous
`docker compose build`s fight over RAM and can starve Postgres. Both `deploy.sh`
files take this lock. If you rewrite either, keep it: **a lock only one side holds
serializes nothing.**

**`collectstatic`.** Whitenoise uses `CompressedManifestStaticFilesStorage`, which
raises on every request for an asset missing from `staticfiles.json`, and
`staticfiles/` is gitignored — so a `git pull` never brings it. Skip this step and
every page 500s. (Potum's script has no such step; do not "align" them.)

The healthcheck has two traps baked in:
- `-H "Host: navedafinance.com"` — `ALLOWED_HOSTS` has no `localhost`, so a bare
  request gets `400 DisallowedHost` from a perfectly healthy app.
- `SECURE_REDIRECT_EXEMPT = [r'^healthz$']` in `settings/production.py` — the probe
  is plain HTTP inside the container, and without the exemption Django answers
  `301 → https`, which `curl -f` reports as **success**. A healthcheck that passes
  on a dead app is worse than none.

---

## Repo access for the box

Both repos are private. `deploy.sh` runs `git pull` as the `deploy` user with its
own credentials, so the box holds a standing read credential per repo:

**A GitHub deploy key may only be attached to one repository.** Potum's key was
already bound to potumsite, so naveda got its own, disambiguated by an SSH alias:

```
~/.ssh/naveda_pull          # read-only deploy key on naveda_integra
~/.ssh/config               # Host github-naveda → github.com, IdentityFile naveda_pull
origin = git@github-naveda:CJSuryo/naveda_integra.git
```

Write access is **unchecked** on that key, deliberately: the box only ever pulls,
and a write-capable key would turn a box compromise into a repo compromise.

Verify: `ssh deploy@5.223.77.16 'cd apps/projects/naveda_integra && git fetch --dry-run'`

---

## CI config

Repo → Settings → Secrets and variables → Actions:

| Secret | Value |
|---|---|
| `DEPLOY_HOST` | `5.223.77.16` |
| `DEPLOY_USER` | `deploy` |
| `DEPLOY_SSH_FINGERPRINT` | `SHA256:JVGrKVHFQUEBnQgB/2aek/fSpdV0448rWS1CHYO0G1c` |
| `DEPLOY_SSH_KEY` | private half of `~/.ssh/naveda_deploy` (on the laptop; its public half is in `~deploy/.ssh/authorized_keys`) |

Plus a **`production` environment** (Settings → Environments) — the workflow
declares `environment: production` and the job will not start without it.

**The fingerprint must be the box's ECDSA host key, not its ed25519 one.**
`appleboy/ssh-action` is drone-ssh is Go's `x/crypto/ssh`, whose default host-key
preference puts `ecdsa-sha2-nistp256` first. It never negotiates ed25519, so
pinning that key fails the handshake with `host key fingerprint mismatch`.

Verify rather than trust: `ssh deploy@5.223.77.16 'ssh-keygen -lf /etc/ssh/ssh_host_ecdsa_key.pub'`

Also: `script_stop` is **not** a valid input on `@v1` (it warns and is ignored).
`set -o errexit` in `deploy.sh` is what fails the job.

If a CI run dies before it even connects, the usual cause is a mangled
`DEPLOY_SSH_KEY` — on Windows it must be copied with `-Raw`, or the newlines are
destroyed and GitHub stores an unusable key:
```powershell
Get-Content $env:USERPROFILE\.ssh\naveda_deploy -Raw | Set-Clipboard
```

---

## Operating it

**Deploy:** `git push origin main`. Watch it: GitHub → Actions → deploy.

**Deploy by hand** (bypasses CI entirely; the box is the source of truth):
```bash
ssh deploy@5.223.77.16 'cd apps/projects/naveda_integra && ./deploy.sh'
```

**Where a failure leaves you:**
- Fails at `migrate` → **old code still live**, site keeps serving. Fix forward.
- Fails at the **healthcheck** → new code is live and broken. Roll back.

**Roll back:**
```bash
ssh deploy@5.223.77.16 'cd apps/projects/naveda_integra \
  && git reset --hard <last-good-sha> && ./deploy.sh'
```
Then reset `main` to match, or the next push redeploys the bad commit.

**`git push origin main` is now a production trigger.** Check what `main` actually
carries before pushing — it accumulates unpushed work quietly.

---

## Known-stale, still open

- **No branch protection on `main`** (either repo). Any local push deploys.
- **`pajak` has model changes with no migration.** Prod runs without them;
  `migrate` prints the warning on every deploy. Pre-existing, unrelated to deploy.
- **`ssh-keyscan` is broken in Git Bash** (expands the CIDR, never connects, exits
  0 with empty output). Read host keys from the box over an authenticated session
  instead — strictly more trustworthy anyway, since keyscan believes whatever
  answers on that IP, which is the exact attack the pin exists to stop.
