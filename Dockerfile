# Adopted verbatim from the copy that was living untracked on the production box.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# build-essential + libpq-dev are needed to build psycopg2 / Pillow wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

COPY . .

EXPOSE 8000

# collectstatic is NOT run here: whitenoise uses CompressedManifestStaticFilesStorage,
# and compose bind-mounts the repo over /app anyway, so anything built into the image
# is shadowed at runtime. deploy.sh runs it on the box instead.
CMD ["gunicorn", "naveda_integra.wsgi:application", "--bind", "0.0.0.0:8000"]
