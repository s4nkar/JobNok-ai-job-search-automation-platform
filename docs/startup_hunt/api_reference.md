# Startup Hunt — API Reference

**Base URL**: `/api/v1/startup-hunt`  
**Authentication**: Bearer JWT Token in `Authorization` header.

---

## 1. Search Startup Opportunities

### `POST /api/v1/startup-hunt/search`

Executes startup discovery search against canonical ATS boards, startup maps, and tech signals.

#### Request Body (`application/json`)
```json
{
  "query": "Backend Engineer",
  "location": "Berlin",
  "country": "de",
  "stages": ["Seed", "Series A"],
  "tech_stack": ["Python", "PostgreSQL"],
  "limit": 30
}
```

---

## 2. User Saved Opportunities

### `GET /api/v1/startup-hunt/opportunities`
Lists all opportunities saved by the active user.

### `GET /api/v1/startup-hunt/opportunities/{opportunity_id}`
Fetches detailed metadata, score reasons, citations, and ATS direct apply links for a saved opportunity.

### `POST /api/v1/startup-hunt/opportunities`
Saves an opportunity from the search stream to the user's dashboard.

### `PUT /api/v1/startup-hunt/opportunities/{opportunity_id}`
Updates opportunity status (`saved`, `applied`, `contacted`, `skipped`).

---

## 3. Contacts & Outreach Leads

### `GET /api/v1/startup-hunt/contacts`
Lists contacts (founders, hiring managers) associated with the user's saved opportunities.

- **Query Parameters**:
  - `opportunity_id` (optional string): Filter contacts by specific opportunity.

---

## 4. ATS Board Resolution & Sources

### `POST /api/v1/startup-hunt/sources/resolve`
Triggers async resolution for a company name or careers URL (resolves ATS board slug and website domain).

#### Request Body
```json
{
  "company_or_url": "https://techcorp.com/careers"
}
```

#### Response (`200 OK`)
```json
{
  "source_id": "c81f3a2b-1194-4d88-b219-4820d911a012",
  "name": "TechCorp",
  "company": "TechCorp GmbH",
  "type": "greenhouse",
  "slug": "techcorp",
  "url": "https://boards.greenhouse.io/techcorp",
  "status": "resolved"
}
```
