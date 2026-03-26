## Cloud Run Job (ingest) setup

> **Cheer fork:** Create a **separate** Cloud Run job and secrets (e.g. name `cheer-ingest`) pointing at your **cheer** Postgres instance. The commands below still use example names like `usag-ingest`; substitute your own job/image names.

### Default image command: **cheer only (Varsity scores)**

The **`cheer-ingest`** Docker image default is **`python cheer_ingest_main.py`** (file at service root, next to `ingest.py`). It **does not** run **`ingest.py`**, MSO, or gymnastics Playwright scrapes.

It syncs **Varsity TV event results** (division/round score tables from the event-hub API) into **`cheer_mvp_*`** for meets whose `meet_key` is `VARSITY-<event_id>` and whose **`start_date`…`end_date`** include **today** in **`CHEER_INGEST_TZ`** (default `America/New_York`). Same API supplies scored divisions; there is no separate in-meet “mat schedule” JSON—the broadcast **event ticker** is for TV listings, not rotation order.

**Required**

- `DATABASE_URL` — cheer Postgres (same DB as `cheer-scores-api` for MVP reads)

**Optional**

- `CHEER_INGEST_TZ` — IANA timezone for “today” (default `America/New_York`)
- `CHEER_VAR_EVENT_IDS` — e.g. `14479023,14479024` to sync those events **on every run**, ignoring the date filter (useful for testing or a fixed roster)
- `CHEER_VAR_SYNC_UNDATED_MEETS` — `1` / `true` to also sync `VARSITY-*` rows with **no** `start_date`/`end_date`
- `CHEER_USE_CODE_TARGET_LIST` — set to `0` / `false` to ignore the hardcoded list in `core/cheer_target_meets.py` (DB-only mode)

**Do not put `CHEER_VAR_EVENT_IDS=…` in job “Arguments”.** Cloud Run passes each arg to Python; `cheer_ingest_main.py` will error with `unrecognized arguments`. Set it as an **environment variable** on the job (or use `--event-id` in args — see below).

**Force specific Varsity events (ignore date window)**

- **Env (recommended for Cloud Run):** merge into existing env, e.g.  
  `gcloud run jobs update cheer-ingest --region=us-central1 --project=meet-tracker-490603 --update-env-vars=CHEER_VAR_EVENT_IDS=14478875`  
  Use comma-separated ids for several events. Remove later with `--clear-env-vars` is blunt — prefer setting `CHEER_VAR_EVENT_IDS` empty or removing the key in the console / YAML.
- **Args (alternative):** keep args as **only** `cheer_ingest_main.py` **or** add flags: `--args=cheer_ingest_main.py,--event-id,14478875` (repeat `--event-id` for multiple).

**Code target list (like `TARGET_MEETS` for MSO):** edit `core/cheer_target_meets.py` → `CHEER_TARGET_VAR_EVENTS`. Each row has `event_id`, optional `name`, optional `start_date` / `end_date`. If both dates are omitted, that event is synced **every** scheduled run until you remove it.

**Create / update job (no MSO env vars)**

```bash
gcloud run jobs create cheer-ingest \
  --region=us-central1 \
  --project=meet-tracker-490603 \
  --image=us-central1-docker.pkg.dev/meet-tracker-490603/containers/cheer-ingest:latest \
  --set-secrets=DATABASE_URL=DATABASE_URL:latest \
  --set-env-vars=CHEER_INGEST_TZ=America/New_York \
  --command=python \
  --args=cheer_ingest_main.py \
  --task-timeout=1800

# After rebuild:
gcloud run jobs update cheer-ingest --region=us-central1 --project=meet-tracker-490603 \
  --image=us-central1-docker.pkg.dev/meet-tracker-490603/containers/cheer-ingest:latest
```

Schedule every few minutes on meet days with Cloud Scheduler (same pattern as below). Ensure **`cheer_mvp_meets`** has rows (e.g. `python scripts/ingest_varsity.py --sync-meets` once, or insert `VARSITY-*` meets with correct dates).

**Legacy: gymnastics MSO pipeline (`ingest.py`)**

To run the old **MeetScoresOnline** ingest from this image, override the job command, e.g. `--command=python` and `--args=ingest.py,--scrape-limit,1,--use-target-meets` and set the **MSO_*** env vars from the section below. Prefer a **separate** Cloud Run job (e.g. `usag-ingest`) so cheer and gym never share one template by accident.

---

This project **can also** run as a **Cloud Run Job** that scrapes **MSO (gymnastics)** via **`ingest.py`** and writes into Postgres (original `ingest-meets` behavior).

### Required env vars

- `DATABASE_URL`: Supabase Postgres connection string
- `MSO_TZ`: e.g. `America/New_York`
- `MSO_ONLY_TODAY_SESSIONS`: `1` (recommended)
- `MSO_API_ENABLED`: `0` (recommended)
- (optional) `MSO_DISABLE_RESULT_FINGERPRINT`: set to `1` to **always** run the full scrape (no “no change detected, skipping”). Use if you need a quick workaround; normally the fingerprint includes the **session picker** text so new sessions still invalidate the cache.
- (optional) `MSO_FINGERPRINT_FORCE_SCRAPE_MINUTES`: e.g. `25` — if the fingerprint matches but it has been **longer than this** since `last_changed_at` (last scrape that saved data), run a full scrape anyway. Good insurance during **live** meets if MSO updates scores without changing the fingerprinted HTML much.
- (optional) `MSO_ALWAYS_SCRAPE_ON_MEET_DAYS`: default **`1`** — on any calendar day that falls within the meet’s **`start_date`…`end_date`** in the database (using **`MSO_TZ`**), ingest **does not** fingerprint-skip; it runs a full scrape so live meet days keep polling. Set to `0` to always allow “no change detected, skipping” whenever the hash matches (old behavior).

**Do not** append `MSO_DISABLE_RESULT_FINGERPRINT=1` to the job **args** (e.g. after `ingest.py,...`). That passes a string to `ingest.py`, which then errors with `unrecognized arguments`. Set it as an **environment variable** on the job or on a single execution (see below).

### One-off force scrape (env override, not args)

Merge into **one execution only** (job template unchanged):

```bash
gcloud run jobs execute usag-ingest --region=REGION --update-env-vars=MSO_DISABLE_RESULT_FINGERPRINT=1 --wait
```

If your gcloud version requires a container name: put `--container=CONTAINER_NAME` before `--update-env-vars` (get the name from `gcloud run jobs describe usag-ingest --region=REGION --format='value(spec.template.template.containers[0].name)'`).

### Suggested secrets (Secret Manager)

- `DATABASE_URL`
- (optional) `MSO_USERNAME`, `MSO_PASSWORD` (if you add authenticated scraping later)

### Build & deploy (example commands)

Replace:
- `PROJECT_ID`
- `REGION` (e.g. `us-central1`)
- `REPO` (Artifact Registry repo name, e.g. `containers`)
- `IMAGE` (e.g. `usag-ingest`)

**Same project / registry as cheer-scores-api:** use Cloud Build from repo root (see `cloudbuild.yaml` in this folder):

```bash
gcloud builds submit services/ingest-cheer --config services/ingest-cheer/cloudbuild.yaml
```

That pushes `us-central1-docker.pkg.dev/meet-tracker-490603/containers/cheer-ingest:latest`. Point your Cloud Run Job at that image (or copy the file and change project/repo if you use another GCP project).

**Order matters:** run **`gcloud builds submit`**, then **`gcloud run jobs update … --image=…:latest`**, then **`gcloud run jobs execute`**. Executing before the new image is deployed will still run the old digest.

If you see `can't open file '.../cheer_ingest_main.py'`, the build tarball did not include that file or the job still uses old args (`scripts/…`). This repo adds **`services/ingest-cheer/.gcloudignore`** and an explicit **`COPY cheer_ingest_main.py`** in the Dockerfile so missing uploads fail at build time. Job args must be **`cheer_ingest_main.py`** (not under `scripts/`).

---

### Generic build (manual tag)

```bash
gcloud config set project PROJECT_ID

gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudscheduler.googleapis.com secretmanager.googleapis.com

gcloud artifacts repositories create REPO \
  --repository-format=docker \
  --location=REGION

gcloud builds submit \
  --tag REGION-docker.pkg.dev/PROJECT_ID/REPO/IMAGE:latest \
  .

gcloud secrets create DATABASE_URL --replication-policy="automatic"
gcloud secrets versions add DATABASE_URL --data-file=-

gcloud run jobs create usag-ingest \
  --region=REGION \
  --image=REGION-docker.pkg.dev/PROJECT_ID/REPO/IMAGE:latest \
  --set-secrets=DATABASE_URL=DATABASE_URL:latest \
  --set-env-vars=MSO_TZ=America/New_York,MSO_ONLY_TODAY_SESSIONS=1,MSO_API_ENABLED=0 \
  --command=python \
  --args=ingest.py,--scrape-limit,1,--use-target-meets

# Run once to validate (`--scrape-limit N` = stop after N meets that return at least one score row after dedup; meets with 0 rows do not count)
gcloud run jobs execute usag-ingest --region=REGION

# Scheduler every minute (runs the job)
gcloud scheduler jobs create http usag-ingest-every-minute \
  --location=REGION \
  --schedule="* * * * *" \
  --uri="https://REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/PROJECT_ID/jobs/usag-ingest:run" \
  --http-method=POST \
  --oauth-service-account-email="YOUR_SCHEDULER_SA@PROJECT_ID.iam.gserviceaccount.com"
```

Notes:
- **MSO discovery (listing pages):** By default, `ingest.py --use-target-meets` does **not** call MSO state/search listing URLs (avoids intermittent **403**s and extra load). Turn on listing discovery in any of these ways (first match wins with `disc` / env, then DB):
  - CLI **`--disc`** (e.g. `ingest.py,--use-target-meets,--disc,...`)
  - Env **`ENABLE_TARGET_METADATA_ENRICHMENT=1`**
  - **Database** (no Cloud Run arg change): table **`ingest_settings`**, row **`key = 'discover_mso_listings'`**, **`value`** truthy (`true` / `1` / `yes` / `on`). `create_tables()` creates the table on next ingest. Example:
    ```sql
    INSERT INTO ingest_settings (key, value) VALUES ('discover_mso_listings', 'true')
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
    -- turn off:
    UPDATE ingest_settings SET value = 'false' WHERE key = 'discover_mso_listings';
    ```
  Full discovery mode (no `--use-target-meets`) requires **`--disc`**, that env, **or** the DB flag above.
- The Scheduler-to-Run call requires IAM; easiest path is creating a dedicated service account and granting it `roles/run.invoker` on the job.
- For production, consider setting Job task timeout and retries.
- **Chromium on Cloud Run:** The ingest image sets `PLAYWRIGHT_CHROMIUM_USE_HEADLESS_SHELL=0` so Playwright uses full Chromium instead of `chrome-headless-shell` (the shell binary has crashed with **SIGSEGV** / SwiftShader on some task shapes). Launch args also pass `--no-sandbox`, `--disable-dev-shm-usage`, `--disable-gpu`. If you still see browser crashes, raise task **memory** (e.g. `gcloud run jobs update usag-ingest --region=REGION --memory=2Gi`) and redeploy the image after rebuild.
- **MSO URL host:** MeetScoresOnline can show **different session UIs** for `https://meetscoresonline.com/...` vs `https://www.meetscoresonline.com/...`. Ingest normalizes MSO URLs to **`https://www.meetscoresonline.com`** before fingerprint/scrape so behavior matches the `www` site.
- **Fingerprint schema:** The stored `last_fingerprint` includes an internal **schema version** (default `2`). When that version in code/env differs from what was used when the row was written, the next run **will not** “no change skip” until after a successful scrape updates it. Override with `MSO_FINGERPRINT_SCHEMA_VERSION` if you need to force invalidation without a code change.
- **`--scrape-limit`:** For normal runs (no `--meet` / `--interactive`), the job stops after **that many meets that produced at least one score row** (after dedup). Meets with no URL, **no change detected** skip, errors, or **0 rows** do **not** count, so the job can scan further down `TARGET_MEETS` or the discovery list in the same run.

### MSO session UI (two common shapes) and scraper fallbacks

MeetScoresOnline is **not** consistent across meets or hosts, but most results pages look like **one of these**:

1. **Simple / “www-style”** — Session menu offers **Combined** and/or **01 / 02** under the breadcrumb. One **Combined** table often has everyone for that filter.
2. **Date / flyout** — Menu shows **dates** (e.g. Friday 3/20, Today 3/21); hovering opens **sub-rows** like `01 - Level 6 …`, `02 - Level 6 …`.

**What ingest does**

- **Canonical URL:** All MSO URLs are normalized to **`https://www.meetscoresonline.com/...`** so you don’t randomly get the “other” host’s variant for the same meet.
- **HTML scrape (`mso_scraper`)** runs strategies **in order** (see `_scrape_result_page`):
  1. **Combined** — click **Combined** in the session picker, read tables.
  2. **Nav session tabs** — if Combined produced **fewer than ~30 rows**, look for links like **`Session 02 (42)`** and click each tab, collect rows.
  3. **Session picker items** — if **total rows are still &lt; ~30**, reopen the dropdown and **click each `.session-picker-item`** (skipping “Combined” in that loop). With **`MSO_ONLY_TODAY_SESSIONS=1`**, only items under **today’s date header** (in **`MSO_TZ`**) are used when the menu has dates. After each flyout choice, code tries to **fix Session 01 vs 02** if the breadcrumb didn’t update (`_sync_nav_session_after_picker_click`).
- **If MSO changes scores but the fingerprint string barely moves:** use **`MSO_FINGERPRINT_FORCE_SCRAPE_MINUTES`** or a one-off **`MSO_DISABLE_RESULT_FINGERPRINT=1`** (as env, not args).
- **To scrape every picker row for the meet (not today-only):** set **`MSO_ONLY_TODAY_SESSIONS=0`** (heavier; use when you need all days/sessions).

**Caveat:** If **Combined** returns **≥ ~30 rows** but is **incomplete** for that meet, the scraper may **not** run strategies 2–3. That’s rare; watch logs (`Combined view: N rows` vs expected size).

