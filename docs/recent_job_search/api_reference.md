# Recent Job Search: API Reference

**Base URL**: `/api/v1/job-search`  
**Authentication**: Bearer JWT Token in `Authorization` header.

---

## 1. Search Recent Jobs

### `POST /api/v1/job-search/search`

Executes multi-provider parallel search, applies location scoring, canonical URL deduplication, and returns ranked primary jobs along with unranked bonus finds.

#### Request Body (`application/json`)
```json
{
  "query": "Senior Software Engineer",
  "location": "Berlin",
  "country": "de",
  "posted_within_hours": 48,
  "remote_only": false,
  "result_limit": 30
}
```

| Field | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `query` | string | Yes | - | Search query terms (Max 100 chars). |
| `location` | string | No | `""` | City or region constraint (Max 100 chars). |
| `country` | string | No | `null` | ISO 2-letter country code (`"de"`, `"us"`, `"gb"`, etc). |
| `posted_within_hours` | integer | No | `72` | Filter jobs posted within last N hours. |
| `remote_only` | boolean | No | `false` | Restrict results strictly to remote roles. |
| `result_limit` | integer | No | `50` | Maximum primary job count to return (1-100). |

#### Response (`200 OK`)
```json
{
  "total": 12,
  "query": "Senior Software Engineer",
  "location": "Berlin",
  "country": "de",
  "remaining_searches": 498,
  "jobs": [
    {
      "id": "e4a2c918-912b-4e12-8409-bf2209d81f10",
      "title": "Senior Software Engineer (Python)",
      "company": "TechCorp GmbH",
      "location": "Berlin, Germany",
      "country": "de",
      "description": "We are seeking a Senior Python Engineer...",
      "salary_min": 80000.00,
      "salary_max": 95000.00,
      "apply_url": "https://adzuna.com/land/12345",
      "canonical_url": "https://adzuna.com/land/12345",
      "posted_at": "2026-08-26T14:30:00Z",
      "source": "adzuna",
      "origin_tool": "recent_job_search",
      "score": 0.95,
      "has_applied": false,
      "application_id": null
    }
  ],
  "bonus_jobs": [
    {
      "id": "a901f4c7-1284-482a-9f5b-1188402f1a92",
      "title": "Backend Lead",
      "company": "StartupX",
      "location": "Remote",
      "apply_url": "https://arbeitnow.com/view/startupx-backend-lead",
      "canonical_url": "https://arbeitnow.com/view/startupx-backend-lead",
      "posted_at": "2026-08-27T08:15:00Z",
      "source": "arbeitnow",
      "origin_tool": "recent_job_search_bonus",
      "score": 0.6,
      "has_applied": false,
      "application_id": null
    }
  ]
}
```

#### Error Responses
- `400 Bad Request`: Invalid parameters or invalid country code.
- `429 Too Many Requests`: Rate limit exceeded (burst window or daily limit).
- `500 Internal Server Error`: Backend service error.

---

## 2. Job Search Applications (Tracked Saved/Applied Jobs)

### `GET /api/v1/job-search/applications`
Lists tracked jobs saved or applied by the active user.

- **Query Parameters**:
  - `limit`: integer (1-200, optional)
  - `offset`: integer (default 0)

---

### `POST /api/v1/job-search/applications`
Saves or updates application status for a job listing.

#### Request Body (`application/json`)
```json
{
  "job_url_canonical": "https://adzuna.com/land/12345",
  "job_title": "Senior Software Engineer (Python)",
  "company_name": "TechCorp GmbH",
  "location": "Berlin, Germany",
  "posted_at": "2026-08-26T14:30:00Z",
  "source": "adzuna",
  "application_status": "applied"
}
```

---

### `PUT /api/v1/job-search/applications/{application_id}`
Updates existing application record status (`"saved"`, `"applied"`, `"skipped"`).

---

### `DELETE /api/v1/job-search/applications/{application_id}`
Deletes application status record (`204 No Content`).
