# Smart Templates: API Reference

**Base URL**: `/api/templates`
**Authentication**: Bearer JWT (Clerk) in `Authorization` header, resolved to `user_id` on every request.

---

## 1. List Templates

### `GET /api/templates`

Returns every template owned by the caller (does **not** include prebuilt templates — those are a static frontend array merged in client-side).

#### Response (`200 OK`)
```json
[
  { "id": "...", "user_id": "...", "name": "...", "category": "Follow-Up", "content": "...", "placeholders": ["name"], "use_count": 3, "created_at": "..." }
]
```

#### Error Responses
- `429 Too Many Requests`: burst window exceeded.

---

## 2. Create a Template

### `POST /api/templates`

#### Request (`application/json`)
| Field | Type | Required | Bounds | Description |
| :--- | :--- | :--- | :--- | :--- |
| `name` | string | Yes | 2–100 chars | |
| `category` | string | Yes | one of: `Cold DM - Recruiter`, `Cold DM - Hiring Manager`, `Follow-Up`, `Referral Ask`, `Email Outreach`, `Custom` | |
| `content` | string | Yes | 10–5,000 chars | Use `{{placeholder}}` for dynamic values — extracted automatically, not a request field. |

```json
{ "name": "Recruiter Outreach", "category": "Cold DM - Recruiter", "content": "Hi {{name}}, I'd love to connect." }
```

#### Response (`201 Created`)
Full row, including the server-computed `placeholders` array.

#### Error Responses
- `422 Unprocessable Entity`: a field fails validation (missing, too short, too long, or an unknown `category`).
- `429 Too Many Requests`: daily quota (`rate_limit_templates_create_per_day`, default 50) or burst window exceeded.

---

## 3. Update a Template

### `PUT /api/templates/{id}`

All fields optional — only the ones actually sent are changed (`exclude_unset`, not "sent as null vs. not sent"). Same bounds as §2. `placeholders` is re-extracted automatically if `content` is included. `use_count` is **not** a field here — see §5.

```json
{ "name": "Recruiter Outreach v2" }
```

#### Response (`200 OK`)
The updated row.

#### Error Responses
- `404 Not Found`: template doesn't exist or isn't owned by the caller.
- `422 Unprocessable Entity`: no fields sent, or a sent field fails validation.
- `429 Too Many Requests`: burst window exceeded.

---

## 4. Delete a Template

### `DELETE /api/templates/{id}`

#### Response (`204 No Content`)

#### Error Responses
- `404 Not Found`: template doesn't exist or isn't owned by the caller.
- `429 Too Many Requests`: burst window exceeded.

---

## 5. Record a Use (Atomic Counter)

### `POST /api/templates/{id}/use`

Called when the user copies a filled-in template to the clipboard. Atomically increments `use_count` at the DB layer (`UPDATE ... SET use_count = use_count + 1 RETURNING *`) rather than accepting a client-computed value — see `architecture_lld.md` §3.1 for why.

#### Response (`200 OK`)
The updated row, with the new `use_count`.

#### Error Responses
- `404 Not Found`: template doesn't exist or isn't owned by the caller.
- `429 Too Many Requests`: burst window exceeded.
