# Startup Scout — Data Flow & Schema Reference

**Document Version:** 2.0.0  
**Status:** Approved for Production  

---

## 1. Database Schemas (PostgreSQL)

### 1.1 `startup_scout_companies` Table

Stores discovered startups and their intelligence metadata.

```sql
CREATE TABLE startup_scout_companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    what_they_do TEXT,
    funding_stage TEXT,                           -- Check constraint vocabulary: 'angel', 'pre-seed', 'seed', 'series-a', 'series-b', 'series-c', 'series-d', 'series-e'
    size_range TEXT,
    location TEXT,
    website TEXT,
    linkedin_url TEXT,
    source TEXT NOT NULL DEFAULT 'web_scrape',
    crawl_status TEXT NOT NULL DEFAULT 'pending', -- Check constraint: 'pending', 'crawling', 'enriched', 'partial', 'failed'
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT startup_scout_crawl_status_check 
        CHECK (crawl_status IN ('pending', 'crawling', 'enriched', 'partial', 'failed'))
);

CREATE INDEX startup_scout_companies_user_idx ON startup_scout_companies(user_id);
CREATE INDEX startup_scout_companies_status_idx ON startup_scout_companies(crawl_status);
```

---

### 1.2 `startup_scout_contacts` Table

Stores key personnel (Founders, CEOs, CTOs) associated with discovered startups.

```sql
CREATE TABLE startup_scout_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES startup_scout_companies(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT,
    title TEXT,
    email TEXT,
    linkedin_url TEXT,
    source TEXT,                                  -- 'web_scrape', 'apollo'
    confidence NUMERIC,                           -- Score between 0.0 and 1.0
    source_url TEXT,
    is_verified BOOLEAN,
    verification_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX startup_scout_contacts_user_idx ON startup_scout_contacts(user_id);
CREATE INDEX startup_scout_contacts_company_idx ON startup_scout_contacts(company_id);
```

---

## 2. API DTO Schemas (`schemas.py`)

### 2.1 `ScoutSearchRequest`
```json
{
  "location": "Berlin",
  "funding_stages": ["seed", "series-a"],
  "industry": "AI / Machine Learning",
  "limit": 50
}
```

### 2.2 `SaveCompanyRequest`
```json
{
  "name": "NeuralTech GmbH",
  "description": "Building autonomous AI agents for industrial logistics.",
  "what_they_do": "AI agent platform for warehouse fleet optimization.",
  "funding_stage": "series-a",
  "size_range": "11-50",
  "location": "Berlin, Germany",
  "website": "https://neuraltech.ai",
  "linkedin_url": "https://linkedin.com/company/neuraltech-ai",
  "source": "web_scrape"
}
```
