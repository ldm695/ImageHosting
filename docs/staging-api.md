# Staging API — ImageHosting Upload Confirmation

## Overview

The staging API implements a **two-phase upload workflow**: files are first uploaded to a temporary staging area, then explicitly confirmed (moved to the final directory) or cancelled (deleted). This allows previewing before committing, and handles timeouts with auto-cleanup.

### Why staging instead of direct upload?

| Direct Upload (`POST /api/upload`) | Staging Flow |
|---|---|
| File saved immediately | File goes to temp area first |
| No undo | Can confirm or cancel |
| No expiration | Auto-cleanup after timeout (default 300s) |
| Immediate response | Preivew + confirm flow |

---

## Storage Layout

All staging files live under the server's data directory:

```
{Config.DATA_DIR}/staging/
├── {token}_{safe_filename}    ← the uploaded file
└── {token}.meta.json          ← metadata (original name, target group)
```

- `token` = 32 hex chars (UUID v4 hex)
- `safe_filename` = sanitized filename (stripped of path separators, special chars)
- `Config.DATA_DIR` defaults to `%APPDATA%\ImageHosting\` on Windows

On server startup, any leftover staging files from a previous unclean shutdown are cleaned up automatically.

---

## API Endpoints

### 1. `POST /api/upload/stage` — Upload to Staging

Upload a single file to the staging area. Returns a `token` that must be used in a subsequent `confirm` or `cancel` call.

**Request:**

```
POST /api/upload/stage?group=general
Content-Type: multipart/form-data

files: <file data>
```

| Param | Location | Required | Default | Description |
|---|---|---|---|---|
| `group` | Query string | No | `"general"` | Target group for the image |
| `files` | Form body | Yes | — | Multipart file(s). Only the first file is processed. |

**Success Response (200):**

```json
{
  "token": "a1b2c3d4e5f67890a1b2c3d4e5f67890",
  "filename": "my_photo.jpg",
  "original_name": "My Photo (1).jpg",
  "filename_changed": true,
  "name_conflict": false,
  "group": "general",
  "expires_in": 300,
  "url": "/uploads/general/my_photo.jpg",
  "absolute_path": "C:\\Users\\...\\uploads\\general\\my_photo.jpg",
  "preview": "data:image/jpeg;base64,/9j/4AAQ..."
}
```

| Field | Type | Description |
|---|---|---|
| `token` | string | UUID hex token (32 chars) — required for confirm/cancel |
| `filename` | string | Server-side safe filename (sanitized, no path separators) |
| `original_name` | string | Original filename from client |
| `filename_changed` | bool | Whether `filename` differs from `original_name` (was sanitized) |
| `name_conflict` | bool | Whether a file with the same name already exists in target group |
| `group` | string | Target group |
| `expires_in` | int | TTL in seconds before auto-cleanup |
| `url` | string | Predicted final URL path (relative) |
| `absolute_path` | string | Predicted final disk path (absolute) |
| `preview` | string\|null | Base64 data URL of a 256px thumbnail, or `null` if unsupported |

**Preview behavior:**

- Large images are downscaled to fit within 256×256 (aspect ratio preserved)
- Small images keep their original size (never upscaled)
- Supported formats: PNG, JPEG, GIF, WebP, BMP, SVG
- Unsupported formats return `null`

**Name conflict detection:**

`name_conflict: true` means a file with the same name already exists in the target group. The stage still succeeds (file saved to staging area), but when the frontend sees `name_conflict: true`, it should prompt the user to rename before confirming. Confirm will overwrite the existing file silently.

**Error Responses:**

| Status | Meaning |
|---|---|
| 400 | No file, unsupported format, or invalid parameters |
| 429 | Too many pending uploads (`STAGING_MAX_FILES` = 100 exceeded) |
| 500 | File save or metadata write failure |

**JavaScript Example:**

```javascript
const formData = new FormData();
formData.append('files', fileInput.files[0]);

const res = await fetch('/api/upload/stage?group=' + group, {
  method: 'POST',
  body: formData,
});
const data = await res.json();

// data.preview can be used immediately:
previewImg.src = data.preview;

// Warn if filename was sanitized:
if (data.filename_changed) {
  console.log('Filename sanitized:', data.original_name, '→', data.filename);
}

// Warn if name conflicts with existing file:
if (data.name_conflict) {
  console.log('File "' + data.filename + '" already exists — will overwrite on confirm');
}

// Store token for later confirm/cancel:
const token = data.token;
```

---

### 2. `POST /api/upload/confirm` — Confirm Staged Upload

Move a staged file from the staging area to its final location under `uploads/{group}/`. Generates a thumbnail if the file format supports it.

**Request:**

```
POST /api/upload/confirm
Content-Type: application/json

{
  "token": "a1b2c3d4e5f67890a1b2c3d4e5f67890",
  "group": "pets"
}
```

| Field | Required | Default | Description |
|---|---|---|---|
| `token` | Yes | — | The token returned by `/api/upload/stage` |
| `group` | No | Original group from stage | Override target group |

**Success Response (200):**

```json
{
  "success": true,
  "filename": "my_photo.jpg",
  "group": "pets",
  "url": "/uploads/pets/my_photo.jpg",
  "absolute_path": "C:\\Users\\...\\uploads\\pets\\my_photo.jpg"
}
```

(The response includes all fields from `get_image_info()` if available.)

**Error Responses:**

| Status | Meaning |
|---|---|
| 400 | Missing or invalid token format |
| 404 | Token not found or expired (auto-cleaned after `expires_in` seconds) |
| 500 | File move failure or metadata read failure |

> Name conflict detection is now handled at the **stage** step. Confirm will **overwrite** the existing file silently. Check `name_conflict` in the stage response and prompt the user before confirming.

**JavaScript Example:**

```javascript
const res = await fetch('/api/upload/confirm', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ token: token, group: 'pets' }),
});

if (res.ok) {
  const data = await res.json();
  console.log('Upload confirmed:', data.filename);
}
```

---

### 3. `POST /api/upload/cancel` — Cancel Staged Upload

Remove a staged file and its metadata. Idempotent — calling cancel on an already-expired token succeeds silently.

**Request:**

```
POST /api/upload/cancel
Content-Type: application/json

{
  "token": "a1b2c3d4e5f67890a1b2c3d4e5f67890"
}
```

| Field | Required | Description |
|---|---|---|
| `token` | Yes | The token returned by `/api/upload/stage` |

**Success Response (200):**

```json
{
  "success": true
}
```

**Error Responses:**

| Status | Meaning |
|---|---|
| 400 | Missing or invalid token format |

**JavaScript Example:**

```javascript
await fetch('/api/upload/cancel', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ token: token }),
});
```

---

## Typical Flow

```
User selects file
       │
       ▼
  ┌─────────────────┐
  │ POST /api/upload │
  │ /stage           │ ───→ File saved to staging/{token}_{name}
  └────────┬────────┘       Metadata written to staging/{token}.meta.json
           │                Timer started (expires_in seconds)
           ▼
  ┌─────────────────┐
  │ Show preview     │ ←── data.preview (base64 data URL)
  │ to user          │
  └────────┬────────┘
           │
     ┌─────┴──────┐
     ▼            ▼
  ┌────────┐  ┌────────┐
  │ CONFIRM │  │ CANCEL │
  └────┬───┘  └────┬───┘
       │           │
       ▼           ▼
  ┌──────────┐  ┌──────────┐
  │ Move to   │  │ Delete   │
  │ uploads/  │  │ staged   │
  │ group/    │  │ file     │
  │ Generate  │  │ Remove   │
  │ thumbnail │  │ metadata │
  └──────────┘  └──────────┘
```

### Timeout Behavior

- If neither `confirm` nor `cancel` is called within `expires_in` seconds, the staged file is automatically deleted
- The timer is a daemon thread that does not block server shutdown
- `Config.STAGING_TIMEOUT` defaults to 300 seconds (5 minutes)
- Configurable via Settings UI (`PUT /api/settings/staging-timeout`)

---

## Key Implementation Details

### Thread Safety

```python
_staging_timers: dict[str, threading.Timer] = {}  # token → cleanup timer
_staging_lock = threading.Lock()                    # protects timers dict
```

- All timer operations (add, pop, cancel) are protected by `_staging_lock`
- `confirm` and `cancel` both `pop` the timer — whichever runs first wins, the other gets `None`
- The auto-cleanup callback also `pop`s, preventing double-deletion

### Security

- **Anti-abuse**: Maximum 100 pending uploads at a time (`STAGING_MAX_FILES`)
- **Token validation**: Strict regex `[0-9a-f]{32}` — no path traversal possible
- **Filename sanitization**: `werkzeug.secure_filename()` + manual fallback for non-ASCII names
- **File extension check**: Only `Config.ALLOWED_EXTENSIONS` are accepted
- **Single-file only**: Only the first file from the form is processed, preventing batch abuse through staging

### Preview Generation

- Uses Pillow to open the staged file and generate a 256px thumbnail
- Encoded as base64 data URL for direct use in `<img>` tags
- SVG files are base64-encoded directly (text content)
- Non-thumbnailable formats (e.g. ICO) return `null`
- Format conversion: BMP → PNG, JPEG handles RGBA→RGB conversion

---

## Configuration

Relevant `Config` constants:

| Attribute | Default | Description |
|---|---|---|
| `STAGING_DIR` | `{DATA_DIR}/staging` | Staging file directory |
| `STAGING_TIMEOUT` | `300` | Auto-cleanup timeout (seconds) |
| `STAGING_MAX_FILES` | `100` | Max concurrent pending uploads |
| `ALLOWED_EXTENSIONS` | `{.png, .jpg, .jpeg, .gif, .webp, .svg, .bmp, .ico}` | Accepted file types |
| `PILLOW_FORMATS` | `{.png, .jpg, .jpeg, .gif, .webp, .bmp}` | Formats that can generate thumbnails |
