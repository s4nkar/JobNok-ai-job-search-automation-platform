# Startup Scout — High-Level Architecture (HLD)

**Document Version:** 2.0.0  
**Status:** Approved for Production  
**Target Audience:** AI Systems Engineers, Senior Engineers, Architects  

---

## 1. Executive Overview

**Startup Scout** is an AI-powered intelligence platform that discovers early-to-growth stage technology startups, extracts company profile signals, maps executive contact details (Founders, CEOs, CTOs), and generates customized candidate outreach scorecards using LLM reasoning engines (Gemini/OpenAI).

### Core Objectives
1. **Multi-Source Ecosystem Search**: Queries DuckDuckGo HTML non-JS endpoints across curated startup directories (Crunchbase, EU-Startups, Y Combinator, TechStars, dealroom.co).
2. **Noise Filtering & Domain Blacklisting**: Filters non-company domains (news sites, job boards, blog aggregators, encylopedias) using strict pattern matching (`_NEWS_DOMAINS`, `_SKIP_URL_FRAGMENTS`).
3. **Contact Harvesting & Enrichment**: Dual-phase contact discovery utilizing search snippet regex extraction and Apollo People Search API fallback.
4. **Structured Intelligence Scorecards**: Integrates LLM reasoning (`app.ai.llm`) to generate candidate match scorecards, technology alignment breakdown, and outreach pitch angles.

---

## 2. System Architecture Diagram (Euclidraw Modern Style)

```mermaid
flowchart TD
    User["Web Client / React UI"]
    Router["FastAPI Router (/api/v1/startup-scout)"]

    subgraph DiscoveryEngine ["Phase A: Company Discovery Engine"]
        DDGScraper["DuckDuckGo HTML Engine (html.duckduckgo.com)"]
        DirectoryFilter["Curated Directory Selector (Location + Stage)"]
        DomainBlacklist["Domain & News Filter (_NEWS_DOMAINS)"]
    end

    subgraph ContactEngine ["Phase B: Contact Enrichment"]
        RegexHarvester["Snippet & Title Contact Extractor"]
        ApolloFallback["Apollo People Search API (api.apollo.io)"]
    end

    subgraph IntelligenceLayer ["Phase C: AI Scorecard & Pitch"]
        LLMProvider["LLM Engine / Provider (Gemini / OpenAI)"]
        ScorecardGenerator["Analytical Scorecard Generator"]
    end

    subgraph Storage ["Storage & Cache Layer"]
        DBCompanies["startup_scout_companies Table"]
        DBContacts["startup_scout_contacts Table"]
        RedisCache["Redis Result Cache (TTL 24h)"]
    end

    User --> Router
    Router --> DirectoryFilter
    DirectoryFilter --> DDGScraper
    DDGScraper --> DomainBlacklist

    DomainBlacklist --> RegexHarvester
    RegexHarvester -->|Missing Contact| ApolloFallback
    RegexHarvester -->|Contact Discovered| LLMProvider
    ApolloFallback --> LLMProvider

    LLMProvider --> ScorecardGenerator
    ScorecardGenerator --> DBCompanies
    ScorecardGenerator --> DBContacts
    ScorecardGenerator --> RedisCache
    RedisCache --> Router

    classDef client fill:#e1f5fe,stroke:#0288d1,stroke-width:2px,color:#01579b;
    classDef gateway fill:#fff3e0,stroke:#f57c00,stroke-width:2px,color:#e65100;
    classDef engine fill:#e8f5e9,stroke:#388e3c,stroke-width:2px,color:#1b5e20;
    classDef db fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#4a148c;
    classDef ai fill:#fffde7,stroke:#fbc02d,stroke-width:2px,color:#f57f17;
    classDef ext fill:#fce4ec,stroke:#c2185b,stroke-width:2px,color:#880e4f;

    class User client;
    class Router gateway;
    class DirectoryFilter,DomainBlacklist,RegexHarvester engine;
    class DBCompanies,DBContacts,RedisCache db;
    class LLMProvider,ScorecardGenerator ai;
    class DDGScraper,ApolloFallback ext;
```

---

## 3. High-Level Component Responsibilities

| Component | File Path | Purpose |
| :--- | :--- | :--- |
| **Scout Engine** | `engine.py` | Core 76KB discovery & scraping module executing Phase A directory search and Phase B contact enrichment. |
| **Scout Service** | `service.py` | Database persistence, rate limiting checks, cache key management, and JSON response assembly. |
| **Blacklist Filter** | `engine.py` | Enforces `_NEWS_DOMAINS` (90+ press sites) and `_SKIP_URL_SEGMENTS` to reject articles and retain actual startup profiles. |
| **Apollo Connector** | `engine.py` | Calls Apollo API to fetch verified email addresses and LinkedIn URLs when search snippets lack direct contact details. |
| **LLM Reasoning Adapter**| `app/ai/llm.py` | Generates analytical company summaries, hiring momentum signals, and outreach messaging hooks. |

---

## 4. Multi-Phase Processing Sequence

```mermaid
sequenceDiagram
    autonumber
    actor User as Client UI
    participant Router as API Router
    participant Engine as Scout Engine (engine.py)
    participant DDG as DuckDuckGo HTML
    participant Apollo as Apollo API
    participant LLM as LLM Reasoning
    participant DB as PostgreSQL

    User->>Router: POST /api/v1/startup-scout/search (location='Berlin', stages=['seed'])
    Router->>Engine: search_startups()
    Engine->>DDG: Site query: "site:crunchbase.com/organization Berlin seed"
    DDG-->>Engine: Raw HTML Search Results
    Engine->>Engine: Filter out news domains & non-profile URLs
    Engine->>DDG: Search contacts: "Founder OR CEO Berlin [company]"
    alt Snippet contains contact email
        Engine->>Engine: Extract name, title, email
    else Snippet contact missing
        Engine->>Apollo: POST /v1/mixed_people/search
        Apollo-->>Engine: Verified Executive Contact
    end
    Engine->>LLM: Generate company scorecard & outreach angles
    LLM-->>Engine: JSON Scorecard Payload
    Engine->>DB: Save to startup_scout_companies & contacts
    Engine-->>Router: Response Payload
    Router-->>User: 200 OK (Enriched Scorecards)
```
