/**
 * Central query key registry. Using the same key for the same resource
 * across different pages (e.g. /api/templates on both the Dashboard and the
 * Templates page) means a mutation on one page invalidates the other's
 * cached data too, not just its own.
 */
export const queryKeys = {
  profile: ['profile'] as const,
  tracker: ['tracker'] as const,
  templates: ['templates'] as const,
  campaigns: ['campaigns'] as const,
  campaignRecipients: (campaignId: string) => ['campaigns', campaignId, 'recipients'] as const,
  toolUsage: ['usage', 'tools'] as const,
  startupHuntOpportunities: ['startup-hunt', 'opportunities'] as const,
  startupHuntArtifactCounts: ['startup-hunt', 'artifact-counts'] as const,
  startupHuntSources: ['startup-hunt', 'sources'] as const,
  opportunityArtifacts: (opportunityId: string) => ['startup-hunt', 'opportunities', opportunityId, 'artifacts'] as const,
  startupScoutCompanies: ['startup-scout', 'companies'] as const,
  startupScoutCompany: (companyId: string) => ['startup-scout', 'companies', companyId] as const,
  scoutContacts: (companyId: string) => ['startup-scout', 'companies', companyId, 'contacts'] as const,
  jobSearchApplications: ['job-search', 'applications'] as const,
}
