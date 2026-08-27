# Startup Hunt: High-Level Architecture (HLD)

**Document Version:** 2.0.0  
**Status:** Approved for Production  
**Target Audience:** Principal Architects, Lead Crawling Engineers, Backend Engineers  

---

## 1. Executive Overview

**Startup Hunt** is the automated startup discovery, ATS (Applicant Tracking System) job board resolver, and direct job vacancy ingestion engine. It discovers emerging tech startups across international directories, identifies ATS platforms (Greenhouse, Lever, Ashby, Personio, Workable, etc.), resolves career portals, and continuously ingests active job opportunities via async workers.

### Core Objectives
1. **Automated ATS Board Resolution**: Dynamically maps company domains to proprietary ATS platform endpoints or generic HTML crawler paths.
2. **SSRF Guarded Web Scraping**: Protects infrastructure against Server-Side Request Forgery via strict IP pinning, private subnet rejection (`ssrf_guard`), and HTTP header spoofing prevention.
3. **Decoupled Worker Lifecycle**: Multi-worker background pipeline (`discovery_worker`, `resolution_worker`, `sync_worker`, `backfill_worker`) backed by Celery/Redis queue.
4. **Global Company Registry**: Deduplicated canonical catalog (`CompanyRegistry`) tracking startup growth, ATS board type, crawl priority, and live vacancies.

---

## 2. System Architecture Diagram (Euclidraw Modern Style)

```mermaid
flowchart TD
    User["Web Client / React UI"]
    APIRouter["FastAPI Router (/api/v1/startup-hunt)"]

    subgraph DiscoveryLayer ["1. Startup Discovery"]
        StartupMap["StartupMap Discovery Engine"]
        GoogleWeb["Google Web / Site Search"]
        TheirStack["TheirStack Technology Signals"]
    end

    subgraph WorkerPipeline ["2. Distributed Worker Pipeline"]
        DiscoveryWorker["Discovery Worker (Ingests Seed Domains)"]
        ResolutionWorker["Resolution Worker (Maps ATS & Careers URLs)"]
        SyncWorker["Sync Worker (Polls ATS Boards & Ingests)"]
        BackfillWorker["Backfill Worker (Enriches Contact Data)"]
    end

    subgraph SecurityGuard ["3. SSRF & Ingestion Guard"]
        SSRFGuard["SSRF Guard (IP Pinning & Subnet Block)"]
        GenericCrawler["Generic HTML Crawler (DOM Parser)"]
    end

    subgraph Connectors ["4. Proprietary ATS Connectors"]
        Greenhouse["Greenhouse API / Board"]
        Lever["Lever API / Board"]
        Ashby["Ashby HQ API"]
    end

    subgraph Persistence ["5. Storage Layer"]
        CompanyReg["CompanyRegistry Table (Global Index)"]
        UserSaved["StartupHuntCompany / Opportunities"]
        JobsCache["Shared Jobs Table (Cached Listings)"]
    end

    User --> APIRouter
    APIRouter --> UserSaved
    DiscoveryLayer --> DiscoveryWorker
    DiscoveryWorker --> CompanyReg
    CompanyReg --> ResolutionWorker

    ResolutionWorker --> SSRFGuard
    SSRFGuard --> Connectors
    SSRFGuard --> GenericCrawler

    Connectors --> SyncWorker
    GenericCrawler --> SyncWorker

    SyncWorker --> JobsCache
    BackfillWorker --> UserSaved

    classDef client fill:#e1f5fe,stroke:#0288d1,stroke-width:2px,color:#01579b;
    classDef gateway fill:#fff3e0,stroke:#f57c00,stroke-width:2px,color:#e65100;
    classDef worker fill:#e8f5e9,stroke:#388e3c,stroke-width:2px,color:#1b5e20;
    classDef db fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#4a148c;
    classDef external fill:#fce4ec,stroke:#c2185b,stroke-width:2px,color:#880e4f;
    classDef security fill:#ffe0b2,stroke:#f57c00,stroke-width:2px,color:#e65100;

    class User client;
    class APIRouter gateway;
    class DiscoveryWorker,ResolutionWorker,SyncWorker,BackfillWorker worker;
    class CompanyReg,UserSaved,JobsCache db;
    class StartupMap,GoogleWeb,TheirStack,Greenhouse,Lever,Ashby external;
    class SSRFGuard,GenericCrawler security;
```

---

## 3. High-Level Component Breakdown

| Component | Module Location | Purpose |
| :--- | :--- | :--- |
| **Engine Orchestrator** | `engine.py` | Core 173KB orchestrator managing discovery queries, company resolution, and contact harvesting. |
| **ATS Resolver** | `ingestion/ats_resolver.py` | Inspects HTTP headers, meta tags, and URL redirects to identify ATS platform type (Greenhouse, Lever, Ashby). |
| **SSRF Guard** | `ingestion/ssrf_guard.py` | Validates target URLs before fetching; resolves DNS to reject RFC 1918 private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.1`). |
| **Discovery Workers** | `workers/discovery_worker.py` | Ingests new startup domains into `company_registry` status `'discovered'`. |
| **Resolution Workers**| `workers/resolution_worker.py` | Processes `'discovered'` companies, executes ATS detection, advances state to `'resolved'`. |
| **Sync Workers** | `workers/sync_worker.py` | Periodically fetches active job postings for `'active'` companies and populates `jobs` cache. |
| **Contact Enricher** | `engine.py` (Phase B) | Resolves founder/CEO/CTO contacts via DuckDuckGo HTML scraping and Apollo fallback API. |

---

## 4. ATS Resolution Workflow & State Machine

```mermaid
stateDiagram-v2
    [*] --> Discovered: Domain Ingested
    Discovered --> Resolving: ResolutionWorker Picked Up
    Resolving --> Resolved: ATS Board / Careers Page Found
    Resolving --> NoCareersPage: No Career Portal Exists
    Resolving --> Failed: DNS Error / Timeout / 404

    Resolved --> Active: Initial Job Crawl Succeeded
    Resolved --> NoJobs: Portal Valid, 0 Postings Found

    Active --> Syncing: Periodic SyncWorker Triggered
    Syncing --> Active: Job Ingestion Completed
    Syncing --> Disabled: Persistent HTTP 403 / 410 / Blocking
```
