# ImageHosting API Reference

Base URL: `http://<host>:<port>`

**CORS:** cross-origin browser requests are rejected by default (same-origin only). To allow other origins, add their ports via `PUT /api/settings/allowed-ports` — the check is evaluated per request, so changes apply without a restart.

**Host-only endpoints:** administrative / destructive endpoints may only be called from the host machine (loopback: `127.0.0.1` / `::1`). A LAN client calling them gets `403 {"error": "This action is only allowed from the host machine"}`. These are: `POST /api/shutdown`, `POST /api/settings/browse`, `PUT /api/settings/data-dir`, `PUT /api/settings/port`, `PUT /api/settings/allowed-ports`, and `DELETE /api/groups/<name>`.

**Served images:** every image response carries `X-Content-Type-Options: nosniff`. SVGs additionally get `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; sandbox` so an uploaded SVG can't run scripts if opened directly.

---

## Images

### GET /api/images

List images in a group.

**Query params:** `group` (default `general`), `tag` (optional filter)

**Response:**
```json
{
  "images": [
    {
      "filename": "photo.jpg",
      "group": "general",
      "url": "/uploads/general/photo.jpg",
      "thumbnail_url": "/thumbnails/general/photo.jpg",
      "absolute_path": "C:\\...\\uploads\\general\\photo.jpg",
      "size": 245760,
      "formatted_size": "240.0 KB",
      "width": 1920,
      "height": 1080,
      "created": "2026-07-18T10:21:13.000000",
      "created_formatted": "2026-07-18 10:21",
      "tag": "screenshot"
    }
  ],
  "tags": ["meme", "photo", "screenshot"]
}
```

`thumbnail_url` points at the `/thumbnails/...` route, which falls back to the original file when no thumbnail exists (SVG/ICO). `tag` and `width`/`height` are present only when applicable.

---

### POST /api/upload

Upload images. Supports single or multiple files.

**Query params:** `group` (default `general`)

**Body:** `multipart/form-data`
- `files` — image files
- `filenames` — JSON array of custom filenames (optional, same order as files)
- `tag` — single tag applied to every uploaded file (optional, validated; 400 if invalid)
- `tags` — JSON array of per-file tags (optional, same order as files; takes precedence over `tag`, invalid entries are skipped)

**Response:**
```json
{
  "uploaded": [{ "filename": "cat.png", ... }],
  "errors": [{ "filename": "bad.exe", "error": "Unsupported format..." }]
}
```

---

## Single Image Operations

### DELETE /api/image/{filename}

Delete an image (original + thumbnail).  
**Query:** `group`

### PUT /api/image/{filename}/rename

Rename an image (extension must stay the same).  
**Query:** `group`  
**Body:** `{ "new_name": "new-filename.jpg" }`

### PUT /api/image/{filename}/move

Move an image to another group.  
**Query:** `group` (source)  
**Body:** `{ "to_group": "memes" }`

---

## Tags

Tags are stored per-group in `uploads/{group}/.tags.json` (one tag per image).

### PUT /api/image/{filename}/tag

Set or update the tag for an image.  
**Query:** `group`  
**Body:** `{ "tag": "screenshot" }`  
**Response:** `{ "success": true, "tag": "screenshot", "info": {...} }`

### DELETE /api/image/{filename}/tag

Remove the tag from an image.  
**Query:** `group`

### PUT /api/tags/{tag}

Rename a tag globally (across all images in the group).  
**Query:** `group`  
**Body:** `{ "new_tag": "screenshots" }`  
**Response:** `{ "success": true, "old_tag": "screenshot", "new_tag": "screenshots", "updated": 12 }`

### DELETE /api/tags/{tag}

Remove a tag from all images in the group.  
**Query:** `group`  
**Response:** `{ "success": true, "tag": "screenshot", "removed": 5 }`

---

## Batch Operations

### POST /api/images/batch-delete

**Body:** `{ "group": "general", "files": ["a.jpg", "b.png"] }`

### POST /api/images/batch-move

**Body:** `{ "group": "general", "to_group": "memes", "files": ["a.jpg"] }`

### POST /api/images/batch-tag

Apply the same tag to multiple images.  
**Body:** `{ "group": "general", "files": ["a.jpg", "b.png"], "tag": "photo" }`  
**Response:** `{ "success": true, "tag": "photo", "tagged": ["a.jpg", "b.png"], "errors": [] }`

---

## Staging (Upload Confirmation)

### POST /api/upload/stage

Upload a file to staging (not saved until confirmed).  
**Query:** `group`, `tag` (optional preset tag, applied on confirm)  
**Body:** `multipart/form-data` — `files` (`tag` also accepted as a form field)  
**Response:**
```json
{
  "token": "uuid",
  "filename": "photo.jpg",
  "group": "general",
  "tag": "vacation",
  "url": "/uploads/general/photo.jpg",
  "absolute_path": "C:\\...\\uploads\\general\\photo.jpg",
  "preview": "data:image/jpeg;base64,...",
  "timeout": 300
}
```

### POST /api/upload/confirm

Confirm a staged upload — moves file to final directory and applies the tag.  
**Body:** `{ "token": "uuid", "group": "optional-override", "tag": "optional-override" }`  
The `tag` overrides the staged preset; pass `""` to clear it, omit to keep it. See `docs/staging-api.md` for details.

### POST /api/upload/cancel

Cancel a staged upload — removes temp file.  
**Body:** `{ "token": "uuid" }`

---

## Groups

### GET /api/groups

List all groups with image counts.
```json
[{ "name": "general", "count": 42 }, { "name": "memes", "count": 7 }]
```

### POST /api/groups

Create a new group.  
**Body:** `{ "name": "screenshots" }`

### PUT /api/groups/{name}

Rename a group.  
**Body:** `{ "new_name": "photos" }`

### DELETE /api/groups/{name}

Delete a group and all its images (cannot delete `general`).

---

## Settings

### GET /api/settings

```json
{
  "data_dir": "C:\\Users\\...\\AppData\\Roaming\\ImageHosting",
  "port": 6951,
  "staging_timeout": 300,
  "theme": "auto",
  "allowed_origin_ports": [3000, 8080]
}
```

### PUT /api/settings/data-dir

Change storage directory with automatic file migration.  
**Body:** `{ "data_dir": "D:\\NewPath" }`

### PUT /api/settings/staging-timeout

Change staging timeout (seconds, 10–3600).  
**Body:** `{ "staging_timeout": 600 }`

### PUT /api/settings/port

Change port (takes effect on next restart). Returns `400` if the port is already in use or out of range (1024–65535).  
**Body:** `{ "port": 8080 }`

### PUT /api/settings/allowed-ports

Set the CORS origin port allowlist. Applies immediately — **no restart**. Persisted to `settings.json`. Each port permits browser requests from `http(s)://{localhost|127.0.0.1|LAN-IP}:{port}`. An empty list means same-origin only.  
**Body:** `{ "allowed_origin_ports": [3000, 8080] }`  
Returns `400` for a non-list value or any port outside 1–65535.

### PUT /api/settings/theme

Change theme preference.  
**Body:** `{ "theme": "auto" }` — one of `auto`, `light`, `dark`

### POST /api/settings/browse

Open native folder-picker dialog. Returns `{ "path": "D:\\..." }`.

---

## System

### GET /api/status

Health check. `{ "status": "running", "port": 6951 }`

### POST /api/shutdown

Shut down the server (used for tray restart). Applies pending port from settings.json.

---

## Static Files

### GET /uploads/{group}/{filename}

Serve original image.

### GET /thumbnails/{group}/{filename}

Serve thumbnail (falls back to original if thumbnail is missing).

---

## Error Response Format

All endpoints return errors as:

```json
{ "error": "Human-readable error message" }
```

HTTP status codes: `400` (bad request), `404` (not found), `409` (conflict), `413` (file too large), `500` (server error).
