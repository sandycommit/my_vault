# My Vault 🔐

A private, single-user personal storage app: a chat-like feed (think
WhatsApp/Telegram "message yourself") where every note, link, code snippet, or
uploaded file becomes a chronological, searchable entry in your own vault.

Built as traditional server-rendered Django (MVT) — no REST API, no SPA
framework. Vanilla JavaScript is used only for UX polish (infinite scroll,
drag-and-drop, toasts, confirm dialogs); every core action also works as a
plain HTML form POST if JavaScript is disabled.

## Architecture at a glance

```
PostgreSQL              -> metadata, note/code text, file metadata, search index
Filesystem (MEDIA_ROOT) -> actual uploaded file bytes
```

Uploaded file **bytes never touch PostgreSQL** — only their path, SHA-256
hash, size, and MIME type are stored as metadata. This keeps the database
small even with a large media library; see [Storage design](#storage-design)
below.

---

## 1. Requirements

- Python 3.12+
- PostgreSQL 14+ (any version with `django.contrib.postgres` full-text search
  support)
- pip / venv

## 2. PostgreSQL setup

Create a database and a role for the app (adjust the password):

```sql
CREATE DATABASE my_vault;
CREATE USER my_vault_app WITH PASSWORD 'change-me';
GRANT ALL PRIVILEGES ON DATABASE my_vault TO my_vault_app;
```

On modern PostgreSQL (15+) you may also need, connected to `my_vault`:

```sql
GRANT ALL ON SCHEMA public TO my_vault_app;
```

## 3. Python virtual environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

## 4. Installation

```bash
pip install -r requirements.txt
```

Only three third-party packages are used: `Django`, `psycopg` (PostgreSQL
driver), and `Pillow` (thumbnail generation).

## 5. Environment variables

Copy the example file and edit it:

```bash
cp .env.example .env
```

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Django secret key | *(must be set for production)* |
| `DEBUG` | Debug mode | `False` |
| `ALLOWED_HOSTS` | Comma-separated hostnames | `127.0.0.1,localhost` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL connection | — |
| `DB_CONN_MAX_AGE` | Persistent DB connection lifetime (seconds) | `60` |
| `MAX_UPLOAD_SIZE_MB` | Maximum upload size | `512` |
| `PAGE_SIZE` | Items per page (chat/favorites/trash/search) | `50` |
| `THUMBNAILS_ENABLED` | Generate image thumbnails | `True` |
| `THUMBNAIL_MAX_DIMENSION` | Max thumbnail width/height (px) | `480` |
| `THUMBNAIL_MAX_SOURCE_MB` | Skip thumbnailing images larger than this | `25` |
| `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | Production-only HTTPS enforcement | `False` |

`.env` is loaded by `config/settings.py` itself (a small built-in parser —
no extra dependency) and is git-ignored. **Never commit `.env`.**

## 6. Migrations

```bash
python manage.py migrate
```

This creates the single `vault_vaultitem` table plus its indexes, including
a GIN index on the full-text search vector.

## 7. Creating the vault owner

There is no public signup page — this app is designed for exactly one
private user. Create that account interactively:

```bash
python manage.py create_vault_user
```

You'll be prompted for a username/email and a password (validated against
Django's standard password rules). The account is also a superuser, so the
same login works for `/admin/`.

## 8. Running the development server

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` and sign in.

## 9. Static files

In development, `runserver` serves `static/` automatically. In production,
run:

```bash
python manage.py collectstatic
```

and serve `STATIC_ROOT` (`staticfiles/`) via your web server / reverse proxy.

## 10. Media files

Uploaded files live under `media/uploads/YYYY/MM/DD/<random-name>.<ext>` and
generated image thumbnails under `media/thumbnails/...`. In development,
Django serves `MEDIA_ROOT` automatically only when `DEBUG=True`. In
production, serve `media/` directly from your web server (nginx, etc.) —
**with access control**, since `vault/views.py`'s download/preview views are
the only things that check ownership; a misconfigured direct-serve of
`media/` would bypass that. The simplest safe production setup is to *not*
expose `media/` publicly at all and let Django's `item_download`/`item_raw`
views stream files (fine at personal-vault scale), or use your web server's
internal-redirect mechanism (e.g. nginx `X-Accel-Redirect`) gated behind the
same ownership check.

## 11. Upload configuration

- `MAX_UPLOAD_SIZE_MB` (`.env`) is enforced twice: a fast early rejection by
  `vault.middleware.MaxUploadSizeMiddleware` (checks `Content-Length` before
  reading the body, returns `413`), and a precise check in
  `FileUploadForm.clean_file`.
- A small denylist of directly-executable extensions (`.exe`, `.msi`, `.bat`,
  `.ps1`, `.dll`, …) is rejected outright — see `BLOCKED_UPLOAD_EXTENSIONS`
  in `vault/services.py`.
- Duplicate uploads (matched by SHA-256) reuse the existing physical file
  instead of writing a second copy — see [Deduplication](#deduplication).

## 12. PostgreSQL backup

A `pg_dump` backs up **metadata and text only** — it does not include
uploaded files.

```bash
pg_dump -U my_vault_app -h 127.0.0.1 -F c my_vault > my_vault_db.dump
```

Restore:

```bash
pg_restore -U my_vault_app -h 127.0.0.1 -d my_vault --clean my_vault_db.dump
```

## 13. Media backup

Back up the `media/` directory separately (it's the *only* copy of your
uploaded file bytes):

```bash
tar -czf my_vault_media.tar.gz media/
```

Restore by extracting it back into place before running `migrate` against
the restored database, so file paths referenced by `VaultItem` rows line up
with what's on disk.

**A database backup without a media backup is incomplete, and vice versa —
back up both, together, on the same schedule.**

## 14. Production deployment

- Set `DEBUG=False`, a real `SECRET_KEY`, and a real `ALLOWED_HOSTS`.
- Set `SECURE_SSL_REDIRECT=True`, `SESSION_COOKIE_SECURE=True`,
  `CSRF_COOKIE_SECURE=True` once you're behind HTTPS (HSTS is enabled
  automatically whenever `DEBUG=False`).
- Run behind a real WSGI/ASGI server (gunicorn/uvicorn) behind nginx or
  similar; don't use `runserver` in production.
- Run `python manage.py collectstatic` and serve `staticfiles/` directly from
  your web server.
- See [Media files](#10-media-files) above for how to serve `media/` safely.
- Watch the storage budget: open `/settings/` (or run
  `python manage.py cleanup_vault`) periodically — see
  [Storage design](#storage-design).

## 15. Security considerations

- **Authentication**: Django's built-in session auth; no public registration.
- **Authorization**: every item view filters by `user=request.user` at the
  ORM level; a mismatched owner returns a plain `404`, never a `403` —
  so a user can't tell "doesn't exist" from "isn't yours" by probing IDs.
- **CSRF**: enforced on every state-changing endpoint (Django's
  `CsrfViewMiddleware` + `{% csrf_token %}` in every form).
- **XSS**: user text is never marked `|safe`; Markdown/HTML is never
  rendered from user input. Uploaded SVGs (which can embed `<script>`) are
  never served inline — only as a forced download — and are excluded from
  automatic "image" classification.
- **Path traversal**: uploaded files are never stored under their original
  name — storage paths are always a fresh random UUID plus the file's
  extension, so a crafted `../../etc/passwd` filename cannot escape
  `MEDIA_ROOT`.
- **Upload validation**: extension + MIME cross-checked (the client's
  declared `Content-Type` is never trusted alone), empty files rejected,
  size-capped twice (middleware + form).
- **Open redirect**: the "return to previous page" behavior on
  favorite/delete/restore actions validates the target with
  `url_has_allowed_host_and_scheme` before redirecting.

---

## Storage design

### Why PostgreSQL only stores metadata

The database holds: user rows, `VaultItem` metadata (type, timestamps,
favorite/trash flags), note/code/link **text**, file metadata (original
filename, generated path, MIME type, size, SHA-256 hash), and the full-text
search vector. It never holds file bytes, thumbnails, or rendered HTML.

### Deduplication

On upload, the file is hashed (SHA-256, streamed in chunks — never fully
loaded into memory) before anything is written to disk. If the same user has
already uploaded an identical file, the new `VaultItem` row simply points at
the existing physical file (no second copy written). When an item is
permanently deleted, the physical file is only removed if no other
`VaultItem` row still references it (see `delete_physical_file_if_orphaned`
in `vault/services.py`).

### Full-text search

Search uses PostgreSQL's built-in full-text search
(`SearchVector`/`SearchQuery`/`SearchRank`) against a GIN-indexed
`search_vector` column — not `content__icontains`, which would force a full
table scan on every keystroke as the vault grows. The vector is recomputed
(via a single `UPDATE ... SET search_vector = ...` expression) only when
text/filename/tags actually change, weighted: note/code content (A) >
filename (B) > tags (C) > MIME type (D). Results are ranked by relevance,
then recency.

### Pagination / infinite scroll

The main chat view loads only the most recent `PAGE_SIZE` items and expands
upward via a small AJAX endpoint (`/load-more/`) that returns an HTML
partial — not JSON. Favorites, Trash, and Search use standard
paginated pages (`?page=2`) so they also work with JavaScript disabled.

### Monitoring the 500 MB budget

Visit `/settings/` to see current database size (via
`pg_database_size()`), item counts, and filesystem usage — computed on
demand, not on every request. Run:

```bash
python manage.py cleanup_vault
```

to get the same report from the command line, plus a list of orphaned
files under `media/` (files on disk no longer referenced by any
`VaultItem` — e.g. left behind by an interrupted request). Pass
`--delete-orphans` to actually remove them; without it, the command only
reports. Trash is **never** auto-emptied by this command or by any
scheduled process — only `/trash/empty/` (explicit user action) removes
trashed items permanently.

---

## Testing

```bash
python manage.py test
```

Tests require a live PostgreSQL connection (Django creates and tears down a
`test_<DB_NAME>` database automatically) — the same `.env` credentials must
have permission to create databases, e.g.:

```sql
ALTER USER my_vault_app CREATEDB;
```

Coverage (`vault/tests/`):

- **Auth** — login, logout, anonymous redirect (`test_auth.py`)
- **Text items** — create, read, edit, soft-delete, restore, permanent
  delete, code-fence/link auto-detection (`test_text.py`)
- **Files** — upload + metadata, empty/oversized/blocked-extension
  rejection, SHA-256 deduplication, ownership-gated download, SVG never
  served inline (`test_files.py`)
- **Favorites** — toggle, favorites-only listing, cross-user protection
  (`test_favorites.py`)
- **Search** — content match, filename match, excludes deleted items,
  per-user isolation, relevance ranking (`test_search.py`)
- **Security** — CSRF enforcement, cross-user access returns 404 (not 403),
  HTML-escaping of note content, `javascript:` URLs never treated as links,
  storage-path traversal safety (`test_security.py`)
- **Query efficiency** — chat/favorites/trash page query counts stay flat
  as item count grows, catching N+1 regressions (`test_queries.py`)

## Project layout

```
my_vault/
├── manage.py
├── config/                # settings, root urlconf, wsgi/asgi
├── vault/                 # the single Django app
│   ├── models.py          # VaultItem
│   ├── forms.py           # TextItemForm / EditItemForm / FileUploadForm
│   ├── views.py           # thin request/response layer
│   ├── services.py        # hashing, dedup, thumbnails, type/text detection
│   ├── search.py           # PostgreSQL full-text search query
│   ├── middleware.py       # early oversized-upload rejection (413)
│   ├── admin.py
│   ├── management/commands/{create_vault_user,cleanup_vault}.py
│   └── tests/
├── templates/
│   ├── base.html, accounts/login.html, errors/{400,403,404,413,500}.html
│   └── vault/{chat,favorites,trash,search,settings,item_detail,item_edit}.html
│       + partials/ (composer, header, per-type item cards, …)
│       + components/ (favorite/delete/download buttons, item card)
├── static/{css,js}/
└── media/{uploads,thumbnails}/    # git-ignored — actual file bytes live here
```
