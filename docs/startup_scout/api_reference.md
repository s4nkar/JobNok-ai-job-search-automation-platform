# Startup Scout — API Reference

**Base URL**: `/api/v1/startup-scout`  
**Authentication**: Bearer JWT Token in `Authorization` header.

---

## 1. Discover Startups (Phase A & B)

### `POST /api/v1/startup-scout/search`

Executes multi-directory site search against DuckDuckGo HTML endpoints and extracts executive contacts.

#### Request Body (`application/json`)
```json
{
  "location": "Berlin",
  "funding_stages": ["seed", "series-a"],
  "industry": "Artificial Intelligence",
  "limit": 30
}
```

#### Response (`200 OK`)
```json
{
  "companies": [
    {
      "name": "KiteAI",
      "description": "Next-generation developer workflow automation.",
      "what_they_do": "Automates developer code reviews using LLM agents.",
      "funding_stage": "seed",
      "size_range": "11-50",
      "location": "Berlin, Germany",
      "website": "https://kiteai.dev",
      "linkedin_url": "https://linkedin.com/company/kiteai",
      "contacts": [
        {
          "name": "Sarah Jenkins",
          "title": "Co-Founder & CEO",
          "email": "sarah@kiteai.dev",
          "linkedin_url": "https://linkedin.com/in/sarahjenkins-ceo",
          "confidence": 0.9,
          "source": "apollo"
        }
      ]
    }
  ],
  "count": 1,
  "meta": {
    "cached": false,
    "directories_searched": ["crunchbase.com", "eu-startups.com"],
    "total_raw_found": 14
  }
}
```

---

## 2. Saved Scout Companies

### `POST /api/v1/startup-scout/companies`
Saves a discovered company profile to the user's dashboard.

### `GET /api/v1/startup-scout/companies`
Lists all saved startup company profiles for the current user.

### `GET /api/v1/startup-scout/companies/{company_id}`
Returns details for a single saved company, including enrichment `crawl_status` (`pending`, `crawling`, `enriched`, `failed`).

### `DELETE /api/v1/startup-scout/companies/{company_id}`
Deletes a saved company and cascades deletion to associated contacts.

---

## 3. Enrichment Trigger

### `POST /api/v1/startup-scout/companies/{company_id}/enrich`
Triggers async background deep enrichment for executive contact details and verified email addresses.
