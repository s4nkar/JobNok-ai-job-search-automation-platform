# Build context is the repo root (not apps/web) — required so this Dockerfile
# can see the workspace-level pnpm-lock.yaml/pnpm-workspace.yaml. See
# docker-compose.yml: context: . / dockerfile: apps/web/Dockerfile

FROM node:22-alpine AS deps
WORKDIR /repo
RUN corepack enable && corepack prepare pnpm@11.20.0 --activate
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY apps/web/package.json ./apps/web/package.json
RUN pnpm install --frozen-lockfile

FROM node:22-alpine AS builder
WORKDIR /repo
RUN corepack enable && corepack prepare pnpm@11.20.0 --activate

ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ARG NEXT_PUBLIC_APP_URL
ARG NEXT_PUBLIC_RATE_LIMIT_LINKEDIN
ARG NEXT_PUBLIC_RATE_LIMIT_RESUME
ARG NEXT_PUBLIC_RATE_LIMIT_COVER_LETTER
ARG NEXT_PUBLIC_RATE_LIMIT_INTERVIEW
ARG NEXT_PUBLIC_RATE_LIMIT_SALARY
ARG NEXT_PUBLIC_RATE_LIMIT_JOB_SEARCH
ARG NEXT_PUBLIC_RATE_LIMIT_STARTUP_HUNT
ARG NEXT_PUBLIC_RATE_LIMIT_BULK_CAMPAIGN
ARG NEXT_PUBLIC_RATE_LIMIT_BULK_MONTH
ARG NEXT_PUBLIC_BULK_EMAIL_MIN_DELAY
ARG NEXT_PUBLIC_BULK_EMAIL_DEFAULT_DELAY
ARG NEXT_PUBLIC_LINKEDIN_CACHE_TTL_DAYS

ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL
ENV NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY
ENV NEXT_PUBLIC_APP_URL=$NEXT_PUBLIC_APP_URL
ENV NEXT_PUBLIC_RATE_LIMIT_LINKEDIN=$NEXT_PUBLIC_RATE_LIMIT_LINKEDIN
ENV NEXT_PUBLIC_RATE_LIMIT_RESUME=$NEXT_PUBLIC_RATE_LIMIT_RESUME
ENV NEXT_PUBLIC_RATE_LIMIT_COVER_LETTER=$NEXT_PUBLIC_RATE_LIMIT_COVER_LETTER
ENV NEXT_PUBLIC_RATE_LIMIT_INTERVIEW=$NEXT_PUBLIC_RATE_LIMIT_INTERVIEW
ENV NEXT_PUBLIC_RATE_LIMIT_SALARY=$NEXT_PUBLIC_RATE_LIMIT_SALARY
ENV NEXT_PUBLIC_RATE_LIMIT_JOB_SEARCH=$NEXT_PUBLIC_RATE_LIMIT_JOB_SEARCH
ENV NEXT_PUBLIC_RATE_LIMIT_STARTUP_HUNT=$NEXT_PUBLIC_RATE_LIMIT_STARTUP_HUNT
ENV NEXT_PUBLIC_RATE_LIMIT_BULK_CAMPAIGN=$NEXT_PUBLIC_RATE_LIMIT_BULK_CAMPAIGN
ENV NEXT_PUBLIC_RATE_LIMIT_BULK_MONTH=$NEXT_PUBLIC_RATE_LIMIT_BULK_MONTH
ENV NEXT_PUBLIC_BULK_EMAIL_MIN_DELAY=$NEXT_PUBLIC_BULK_EMAIL_MIN_DELAY
ENV NEXT_PUBLIC_BULK_EMAIL_DEFAULT_DELAY=$NEXT_PUBLIC_BULK_EMAIL_DEFAULT_DELAY
ENV NEXT_PUBLIC_LINKEDIN_CACHE_TTL_DAYS=$NEXT_PUBLIC_LINKEDIN_CACHE_TTL_DAYS

COPY --from=deps /repo/node_modules ./node_modules
COPY --from=deps /repo/apps/web/node_modules ./apps/web/node_modules
COPY . .

RUN pnpm --filter quickjob-frontend build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000

RUN addgroup --system app && adduser --system --ingroup app app

# Next.js standalone output preserves the monorepo-relative path structure
# when built inside a pnpm workspace (server.js lands at apps/web/server.js,
# not flat at the root) — copy targets mirror that nesting.
COPY --from=builder --chown=app:app /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=app:app /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=app:app /repo/apps/web/public ./apps/web/public

USER app
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
