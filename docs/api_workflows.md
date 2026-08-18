# 🔄 API & Tool Workflows

JobNok provides 11 distinct AI-powered tools and features. All tools communicate with the FastAPI backend, which handles logic, caching, AI generation, and database persistence. 

## General Request Flow
1. **Frontend Authentication:** The Next.js client attaches a Supabase JWT to requests sent to `/api/*`.
2. **Backend Validation:** FastAPI validates the JWT, ensuring the `user_id` is present.
3. **Rate Limiting:** Redis checks if the user has exceeded their usage limits for the specific tool.
4. **Processing:** The backend executes the requested logic (e.g., scraping, prompting the LLM).
5. **Database Interaction:** Results are read from or saved to Postgres via SQLAlchemy (Supabase-hosted). App-level `user_id` filtering is the primary access control; RLS is a defense-in-depth backstop, not the enforcement layer.

---

## 1. Smart Templates (`/templates`)
- **Action:** CRUD operations for message templates.
- **Workflow:** 
  - Standard REST operations (Create, Read, Update, Delete) interacting directly with the `templates` table in Supabase.
  - Templates support `{{placeholder}}` syntax for dynamic text replacement.

## 2. LinkedIn Auto-Fill (`/linkedin-fill`)
- **Action:** Scrape a LinkedIn profile and generate a customized message based on a template.
- **Workflow:**
  1. The user provides a LinkedIn URL and a selected Template.
  2. The backend checks the `linkedin_cache` table. If cached data is fresh (within `LINKEDIN_CACHE_TTL_DAYS`), it bypasses scraping.
  3. If not cached, the backend invokes RapidAPI (or PhantomBuster) to scrape the profile. The result is cached.
  4. The scraped data and the template are sent to the AI Provider (Anthropic/HF).
  5. The AI returns a personalized message filling in the template placeholders.

## 3. Resume Tailor (`/resume-tailor`)
- **Action:** Analyze a user's resume against a Job Description (JD).
- **Workflow:**
  1. User uploads a Resume (PDF parsed by PyMuPDF) and pastes a JD.
  2. The backend sends the text to the AI Provider.
  3. The AI returns structured JSON containing:
     - ATS Score
     - Missing Keywords
     - Suggested Bullet Point rewrites.

## 4. Cover Letter Generator (`/cover-letter`)
- **Action:** Generate a cover letter tailored to a JD.
- **Workflow:**
  1. User provides resume data and a Job Description.
  2. AI generates a professional cover letter.
  3. The result is returned for inline editing on the frontend.

## 5. Interview Prep (`/interview-prep`)
- **Action:** Generate role-specific interview questions.
- **Workflow:**
  1. User provides a Job Description.
  2. AI generates 10 STAR-method (Situation, Task, Action, Result) questions and suggested answers specifically tailored for that role.

## 6. Follow-Up Tracker (`/tracker`)
- **Action:** Manage job application statuses and follow-up dates.
- **Workflow:**
  - Standard CRUD operations interfacing with the `job_applications` table.
  - Helps users keep track of the application lifecycle (Applied -> Interview -> Offer/Rejected) and highlights overdue follow-ups.

## 7. Salary Research (`/salary`)
- **Action:** Provide salary estimates and negotiation points based on role and location.
- **Workflow:**
  1. User inputs Job Title and Location.
  2. AI generates a comprehensive response including the median salary, expected range, and specific negotiation talking points.

## 8. Bulk Email Sender (`/bulk-email`)
- **Action:** Send scheduled, batch emails to a list of recipients.
- **Workflow:**
  1. User uploads a CSV and defines an email template.
  2. The frontend creates an `email_campaigns` record and populates `email_recipients` via FastAPI.
  3. FastAPI enqueues one job per recipient to the **ARQ Worker**.
  4. The ARQ worker picks up recipients, processes template variables, and sends emails via the **Resend API**, throttled by a Redis token bucket (`bulk_email_sends_per_second`) shared across all campaigns.
  5. Statuses are updated in the database for a live frontend dashboard.

## 9. Recent Job Search (`/job-search`)
- **Action:** Track jobs discovered or applied to, integrating seamlessly with the Follow-Up Tracker.
- **Workflow:**
  1. Search recent jobs using configured platforms/providers.
  2. Store saved or skipped opportunities in the `job_search_applications` table.
  3. When an opportunity is marked as "applied", the system automatically creates or updates a record in the `job_applications` (Follow-Up Tracker) table.

## 10. Startup Hunt (`/startup-hunt`)
- **Action:** Discover high-potential startups, track contacts, and link specific AI-generated artifacts to leads.
- **Workflow:**
  1. The user inputs search criteria; AI scores and matches startup opportunities against these preferences.
  2. Information is stored in `startup_hunt_companies` and `startup_hunt_opportunities`.
  3. Contacts (such as recruiters or founders) are stored in `startup_hunt_contacts`.
  4. AI-generated docs (resume analysis, cover letters, interview prep) for the specific role are linked via `opportunity_artifacts`.
  5. Like Recent Job Search, applying to a role syncs it directly with the Follow-Up Tracker.

## 11. Profile Management (`/profile`)
- **Action:** Manage user CV details, skills, and personal information for tailored generations.
- **Workflow:**
  1. The user updates personal details stored directly on the `profiles` table.
  2. The user can upload a CV photo, which is pushed securely to the Supabase Storage `cv-photos` bucket, updating the `cv_photo_url` in their profile.
  3. This profile data provides contextual baseline information that can be utilized when querying AI providers for resume or cover letter generation.

---

## AI Provider Abstraction (`app/ai/llm/provider.py`)
All AI interactions are routed through a central `provider.py` module. This module abstracts the underlying LLM provider.
- Governed by the `AI_PROVIDER` environment variable.
- Supported providers: Anthropic (`claude-sonnet`) and HuggingFace (`Mistral-7B`).
- If an AI call fails, the system is designed to retry before throwing an error to the user.
