import { Template } from '@/lib/types'

export const PREBUILT_TEMPLATES: Template[] = [
  // ── Cold DM - Recruiter ──────────────────────────────────
  {
    id: 'pb-recruiter-generic',
    user_id: 'prebuilt',
    name: 'Recruiter — Generic Outreach',
    category: 'Cold DM - Recruiter',
    content: `Hi {{name}},

I came across your profile and noticed you recruit for {{company}}. I'm currently exploring new opportunities as a {{role}} and would love to connect.

I have {{years_experience}} years of experience in {{skills}}. Would you be open to a quick chat this week?

Best,
{{your_name}}`,
    placeholders: ['name', 'company', 'role', 'years_experience', 'skills', 'your_name'],
    use_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    is_prebuilt: true,
  },
  {
    id: 'pb-recruiter-role-specific',
    user_id: 'prebuilt',
    name: 'Recruiter — Role-Specific',
    category: 'Cold DM - Recruiter',
    content: `Hi {{name}},

I saw the {{job_title}} opening at {{company}} and I'm very interested. My background in {{relevant_experience}} aligns well with what you're looking for.

Could we connect to discuss this role further?

Thanks,
{{your_name}}`,
    placeholders: ['name', 'job_title', 'company', 'relevant_experience', 'your_name'],
    use_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    is_prebuilt: true,
  },
  {
    id: 'pb-recruiter-referral',
    user_id: 'prebuilt',
    name: 'Recruiter — Referral Mention',
    category: 'Cold DM - Recruiter',
    content: `Hi {{name}},

{{mutual_connection}} suggested I reach out to you. I'm a {{role}} with {{years_experience}} years of experience at companies like {{past_companies}}.

I'm open to new opportunities and would love to connect. Happy to share my resume if helpful.

Best,
{{your_name}}`,
    placeholders: ['name', 'mutual_connection', 'role', 'years_experience', 'past_companies', 'your_name'],
    use_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    is_prebuilt: true,
  },
  {
    id: 'pb-recruiter-mutual',
    user_id: 'prebuilt',
    name: 'Recruiter — Mutual Connection',
    category: 'Cold DM - Recruiter',
    content: `Hi {{name}},

We're both connected to {{mutual_connection}}, which is how I found you. I'm exploring {{role}} opportunities and noticed you work with companies in {{industry}}.

Would love to be on your radar for relevant roles. I'm happy to send over my profile.

Best,
{{your_name}}`,
    placeholders: ['name', 'mutual_connection', 'role', 'industry', 'your_name'],
    use_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    is_prebuilt: true,
  },

  // ── Cold DM - Hiring Manager ─────────────────────────────
  {
    id: 'pb-hm-direct',
    user_id: 'prebuilt',
    name: 'Hiring Manager — Direct Outreach',
    category: 'Cold DM - Hiring Manager',
    content: `Hi {{name}},

I noticed you lead the {{team}} team at {{company}}. The work your team does on {{specific_project}} really resonates with me — I've done similar work at {{your_company}}.

I'm currently open to new opportunities and would love a quick 15-minute call. Would that work for you?

Best,
{{your_name}}`,
    placeholders: ['name', 'team', 'company', 'specific_project', 'your_company', 'your_name'],
    use_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    is_prebuilt: true,
  },
  {
    id: 'pb-hm-compliment',
    user_id: 'prebuilt',
    name: 'Hiring Manager — Product Compliment',
    category: 'Cold DM - Hiring Manager',
    content: `Hi {{name}},

I've been using {{product_name}} and genuinely impressed by {{specific_feature}}. As a {{your_role}}, I think about these problems a lot.

I'd love to contribute to what you're building. Any chance you have 15 minutes for a quick chat?

{{your_name}}`,
    placeholders: ['name', 'product_name', 'specific_feature', 'your_role', 'your_name'],
    use_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    is_prebuilt: true,
  },
  {
    id: 'pb-hm-shared',
    user_id: 'prebuilt',
    name: 'Hiring Manager — Shared Background',
    category: 'Cold DM - Hiring Manager',
    content: `Hi {{name}},

We share a background in {{shared_background}} — I noticed you were at {{their_past_company}} and I spent {{your_time}} at {{your_past_company}}.

I'm now exploring {{role}} roles and would love to hear how you made the transition to {{company}}. Open to a brief coffee chat?

{{your_name}}`,
    placeholders: ['name', 'shared_background', 'their_past_company', 'your_time', 'your_past_company', 'role', 'company', 'your_name'],
    use_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    is_prebuilt: true,
  },

  // ── Follow-Up ────────────────────────────────────────────
  {
    id: 'pb-followup-1week',
    user_id: 'prebuilt',
    name: 'Follow-Up — 1 Week After Apply',
    category: 'Follow-Up',
    content: `Hi {{name}},

I wanted to follow up on my application for the {{role}} position at {{company}} from last week. I'm still very excited about this opportunity.

Is there any update you can share on the timeline? Happy to provide any additional information.

Thanks,
{{your_name}}`,
    placeholders: ['name', 'role', 'company', 'your_name'],
    use_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    is_prebuilt: true,
  },
  {
    id: 'pb-followup-2week',
    user_id: 'prebuilt',
    name: 'Follow-Up — 2-Week Final Nudge',
    category: 'Follow-Up',
    content: `Hi {{name}},

I applied for the {{role}} role at {{company}} two weeks ago and wanted to check in one last time. I remain very interested and believe I'd be a strong fit based on {{reason}}.

If the role has been filled, no worries at all — I'd love to stay connected for future opportunities.

Best,
{{your_name}}`,
    placeholders: ['name', 'role', 'company', 'reason', 'your_name'],
    use_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    is_prebuilt: true,
  },
  {
    id: 'pb-followup-interview',
    user_id: 'prebuilt',
    name: 'Follow-Up — Post-Interview Thank You',
    category: 'Follow-Up',
    content: `Hi {{name}},

Thank you for taking the time to speak with me about the {{role}} position today. I really enjoyed learning about {{interesting_topic}} and I'm even more excited about the opportunity.

Our conversation reinforced that {{key_takeaway}}. I'd love to continue the conversation.

Best,
{{your_name}}`,
    placeholders: ['name', 'role', 'interesting_topic', 'key_takeaway', 'your_name'],
    use_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    is_prebuilt: true,
  },

  // ── Referral Ask ─────────────────────────────────────────
  {
    id: 'pb-referral-friend',
    user_id: 'prebuilt',
    name: 'Referral Ask — Friend',
    category: 'Referral Ask',
    content: `Hey {{name}},

I saw that {{company}} is hiring for {{role}} and I'm really interested. I know you work there and thought I'd reach out before applying through the portal.

Would you be comfortable referring me? I'd love to chat briefly so you know exactly what I bring to the table.

Thanks so much,
{{your_name}}`,
    placeholders: ['name', 'company', 'role', 'your_name'],
    use_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    is_prebuilt: true,
  },
  {
    id: 'pb-referral-linkedin',
    user_id: 'prebuilt',
    name: 'Referral Ask — LinkedIn Connection',
    category: 'Referral Ask',
    content: `Hi {{name}},

I noticed we're connected on LinkedIn and you work at {{company}}. I'm really interested in the {{role}} opening there and was hoping you might be willing to pass along my resume or put in a referral.

I have {{relevant_background}} and think I could add real value to your team.

Happy to share more details — thanks for considering!

{{your_name}}`,
    placeholders: ['name', 'company', 'role', 'relevant_background', 'your_name'],
    use_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    is_prebuilt: true,
  },
  {
    id: 'pb-referral-warm',
    user_id: 'prebuilt',
    name: 'Referral Ask — Warm Intro Request',
    category: 'Referral Ask',
    content: `Hi {{name}},

I'm trying to connect with {{target_person}} at {{company}} about potential opportunities on their team. I saw you're connected to them on LinkedIn.

Would you be comfortable making a quick introduction? I'm happy to send you a blurb to forward along if that makes it easier.

Thanks so much,
{{your_name}}`,
    placeholders: ['name', 'target_person', 'company', 'your_name'],
    use_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    is_prebuilt: true,
  },

  // ── Email Outreach ───────────────────────────────────────
  {
    id: 'pb-email-recruiter',
    user_id: 'prebuilt',
    name: 'Email — Cold to Recruiter',
    category: 'Email Outreach',
    content: `Subject: {{role}} Candidate — {{years_experience}} Years in {{industry}}

Hi {{name}},

I found your contact through {{source}} and wanted to reach out directly. I'm a {{role}} with {{years_experience}} years of experience, most recently at {{past_company}} where I {{key_achievement}}.

I'm actively looking for my next opportunity and would love to be on your radar. I've attached my resume for your review.

Available for a call anytime — just reply here and we'll find a time.

Best,
{{your_name}}
{{your_linkedin}}`,
    placeholders: ['role', 'years_experience', 'industry', 'name', 'source', 'past_company', 'key_achievement', 'your_name', 'your_linkedin'],
    use_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    is_prebuilt: true,
  },
  {
    id: 'pb-email-founder',
    user_id: 'prebuilt',
    name: 'Email — Cold to Founder',
    category: 'Email Outreach',
    content: `Subject: Helping {{company}} with {{problem_area}}

Hi {{name}},

I've been following {{company}}'s progress — especially {{specific_thing}}. I'm a {{your_role}} who has spent {{years}} years solving exactly the kind of problems you're tackling in {{problem_area}}.

I'd love to explore if there's a fit. Happy to jump on a 20-minute call at your convenience.

Best,
{{your_name}}`,
    placeholders: ['company', 'problem_area', 'specific_thing', 'your_role', 'years', 'name', 'your_name'],
    use_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    is_prebuilt: true,
  },
  {
    id: 'pb-email-conference',
    user_id: 'prebuilt',
    name: 'Email — Conference Follow-Up',
    category: 'Email Outreach',
    content: `Subject: Great meeting you at {{conference_name}}

Hi {{name}},

It was great chatting at {{conference_name}} — I really enjoyed our conversation about {{topic}}.

As I mentioned, I'm exploring {{role}} opportunities and {{company}} seems like a perfect fit given {{reason}}.

Would you be open to continuing the conversation over a quick call?

Best,
{{your_name}}`,
    placeholders: ['conference_name', 'name', 'topic', 'role', 'company', 'reason', 'your_name'],
    use_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    is_prebuilt: true,
  },
  {
    id: 'pb-email-application',
    user_id: 'prebuilt',
    name: 'Email — Cover Letter Style Application',
    category: 'Email Outreach',
    content: `Subject: Application for {{role}} — {{your_name}}

Dear {{name}},

I'm writing to express my strong interest in the {{role}} position at {{company}}. With {{years_experience}} years of experience in {{field}}, I've developed expertise in {{key_skills}}.

In my most recent role at {{past_company}}, I {{key_achievement}}, which I believe directly translates to what you need in this position.

I've attached my resume and would welcome the opportunity to discuss how I can contribute to {{company}}'s goals.

Thank you for your consideration.

Best regards,
{{your_name}}`,
    placeholders: ['role', 'your_name', 'name', 'company', 'years_experience', 'field', 'key_skills', 'past_company', 'key_achievement'],
    use_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    is_prebuilt: true,
  },
  {
    id: 'pb-email-networking',
    user_id: 'prebuilt',
    name: 'Email — Informational Interview Request',
    category: 'Email Outreach',
    content: `Subject: Quick Chat About Your Career at {{company}}?

Hi {{name}},

I came across your profile and was inspired by your career path — particularly your work on {{specific_work}}.

I'm currently transitioning into {{target_field}} and would love to hear about your experience at {{company}}. Would you have 20 minutes for a virtual coffee chat?

I'm flexible and happy to work around your schedule.

Thanks so much,
{{your_name}}`,
    placeholders: ['company', 'name', 'specific_work', 'target_field', 'your_name'],
    use_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    is_prebuilt: true,
  },
]
