#!/usr/bin/env bash
# Runs ON THE BOX. Invoked by .github/workflows/deploy.yml over SSH, or by hand:
#   ssh deploy@5.223.77.16 'cd apps/projects/naveda_integra && ./deploy.sh'
set -o errexit
set -o pipefail

# Serialize against potum's deploy. Both stacks share one 4GB box, and GitHub's
# `concurrency:` group is per-repository — it cannot see across repos. Without
# this, two `docker compose build`s can run at once and starve Postgres.
# NOTE: this only helps once potum's deploy.sh takes the same lock.
exec 9>/tmp/box-deploy.lock
flock 9

git pull --ff-only

# Images build here, not in CI. --memory caps the build so it cannot starve the
# other stack on the box.
docker compose build --memory 1g
docker compose up -d

# Migrations run at DEPLOY time, not build time. A failure here leaves the OLD
# code live and serving — fix forward, do not roll back.
docker compose exec -T web python manage.py migrate --no-input

# Mandatory, not optional: whitenoise uses CompressedManifestStaticFilesStorage,
# which raises on every request for an asset missing from staticfiles.json.
# staticfiles/ is gitignored, so a pull never brings it — only this rebuilds it.
docker compose exec -T web python manage.py collectstatic --no-input

# ManifestStaticFilesStorage loads staticfiles.json into memory once per worker,
# at process boot, and never reloads it. Workers started by `up -d` above can boot
# before this collectstatic call finishes writing the new manifest, so they keep
# serving from a stale/missing manifest until restarted — even though the file on
# disk is already correct. Restart so already-running workers pick it up.
docker compose restart web

echo "Waiting for health..."
for i in $(seq 1 30); do
  # -H Host: ALLOWED_HOSTS has no "localhost", so a bare request gets
  # 400 DisallowedHost from a perfectly healthy app.
  if docker compose exec -T web curl -fsS -H "Host: navedafinance.com" \
       http://localhost:8000/healthz > /dev/null 2>&1; then
    echo "Healthy."
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "UNHEALTHY after 30 tries — new code is live and broken, roll back." >&2
    echo "Check: docker compose logs --tail=100 web" >&2
    exit 1
  fi
  sleep 2
done

docker image prune -f
echo "Deployed: $(git rev-parse --short HEAD)"
