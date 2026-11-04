# Shastho Record: Backend

Prototype backend for a medical record app aimed at countries like Bangladesh that
have no centralized medical record system. Patients upload photos of prescriptions and
lab reports; doctors (with the patient's permission) review them and fill in structured
fields, which marks the record verified. Everything appears on one chronological timeline.

**Stack:** Django, Django REST Framework, SimpleJWT, django-cors-headers, WhiteNoise,
SQLite locally / Postgres in production.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # then set SECRET_KEY
python manage.py migrate
python manage.py seed_demo         # optional demo data
python manage.py runserver
```

Run the tests: `python manage.py test`

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | yes | Django secret key. |
| `DEBUG` | no (default False) | `True` for local development. |
| `ALLOWED_HOSTS` | no | Comma-separated hostnames. |
| `CORS_ALLOWED_ORIGINS` | no | Comma-separated frontend origins, with scheme. |
| `CSRF_TRUSTED_ORIGINS` | no | Backend origin(s) for the admin over HTTPS. |
| `DATABASE_URL` | no | Postgres URL. SQLite is used if empty. |
| `MEDIA_ROOT` | no | Where uploaded images are stored. Use a persistent volume in production. |

## Demo accounts (after `seed_demo`)

Password for all: `DemoPass123!`. Doctors: `dr_anika` (sees only rahim), `dr_karim`
(sees both patients). Patients: `rahim`, `nusrat`. Use `--reset` to rebuild.

## API

All endpoints except register/login need `Authorization: Bearer <access token>`.

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/api/auth/register/` | anyone | Register as patient or doctor |
| POST | `/api/auth/login/` | anyone | Get access and refresh tokens |
| POST | `/api/auth/refresh/` | anyone | Exchange a refresh token for a new access token |
| GET | `/api/auth/me/` | any user | Current user |
| GET, POST | `/api/records/` | patient: own, upload (multipart: `image`, `doc_type`); doctor: granted patients | List / upload |
| GET, PATCH | `/api/records/<id>/` | read: both; PATCH: doctor with access | Review a record; PATCH sets it verified |
| GET | `/api/records/<id>/image/` | same visibility as the record | Authenticated image download |
| GET | `/api/timeline/` | patient: own; doctor: `?patient=<id>` | Records sorted by visit date, else upload date (`?order=asc` to reverse) |
| GET | `/api/doctors/` | patient | Doctors to choose from |
| GET | `/api/patients/` | doctor | Patients who granted me access |
| GET, POST | `/api/access/` | patient | My grants / grant a doctor access (`{"doctor": id}`) |
| POST | `/api/access/<id>/revoke/` | patient | Revoke a grant |

## Security design

- Roles are enforced on the server. A patient can only upload an image and pick a
  `doc_type`; only doctors can write diagnosis, medications, visit date and notes.
- `patient`, `uploaded_by`, `verified_by`, `status` and `created_at` are set from
  `request.user` and never read from the request body.
- One function (`visible_records`) decides which records a user can see, and the list,
  detail, image and timeline all use it. Out-of-scope records return 404.
- Revoking access is immediate and keeps an audit row (`revoked_at`).
- Uploads are checked for real image content (JPEG/PNG/WebP, max 5 MB) and stored under
  random names. Media is never served as public static files.

## Frontend notes

- `<img src>` cannot send an Authorization header. Fetch `image_url` with the token,
  convert the response to a blob, and use `URL.createObjectURL(blob)`.
- Access tokens last 60 minutes; use `/api/auth/refresh/` to renew them.

## Deployment (PythonAnywhere)

1. Clone the repo in a Bash console, create a virtualenv, `pip install -r requirements.txt`.
2. Create `.env` next to `manage.py` with the variables above (`DEBUG=False`).
3. `python manage.py migrate && python manage.py collectstatic --noinput && python manage.py createsuperuser`
4. Web tab: Manual configuration, set the virtualenv and source folder, point the WSGI file at
   `config.settings`, map `/static/` to `staticfiles/`, enable Force HTTPS, then Reload.
5. Do not map `/media/`. Images are served only through the authenticated image endpoint.
6. SQLite is used by default. For Postgres/MySQL, set `DATABASE_URL`.

## Known limitations (prototype)

- Anyone can register as a doctor. A real system would verify credentials (e.g. BMDC).
- No audit log of record views, no pagination, no rate limiting on login.
- Any doctor with access can edit and re-verify a record; the latest editor is recorded.