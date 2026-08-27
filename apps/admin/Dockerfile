# Build context is the repo root (not apps/admin) — required so this
# Dockerfile can see the workspace-level pnpm-lock.yaml/pnpm-workspace.yaml.
# See docker-compose.yml: context: . / dockerfile: apps/admin/Dockerfile

FROM node:22-alpine AS deps
WORKDIR /repo
RUN corepack enable && corepack prepare pnpm@11.20.0 --activate
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY apps/admin/package.json ./apps/admin/package.json
COPY packages/ui/package.json ./packages/ui/package.json
RUN pnpm install --frozen-lockfile

FROM node:22-alpine AS builder
WORKDIR /repo
RUN corepack enable && corepack prepare pnpm@11.20.0 --activate

ARG NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
ARG NEXT_PUBLIC_APP_URL

ENV NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
ENV NEXT_PUBLIC_APP_URL=$NEXT_PUBLIC_APP_URL

COPY --from=deps /repo/node_modules ./node_modules
COPY --from=deps /repo/apps/admin/node_modules ./apps/admin/node_modules
COPY --from=deps /repo/packages/ui/node_modules ./packages/ui/node_modules
COPY . .

RUN pnpm --filter jobnok-admin build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000

RUN addgroup --system app && adduser --system --ingroup app app

# Next.js standalone output preserves the monorepo-relative path structure
# when built inside a pnpm workspace (server.js lands at apps/admin/server.js,
# not flat at the root) — copy targets mirror that nesting.
COPY --from=builder --chown=app:app /repo/apps/admin/.next/standalone ./
COPY --from=builder --chown=app:app /repo/apps/admin/.next/static ./apps/admin/.next/static

USER app
EXPOSE 3000
CMD ["node", "apps/admin/server.js"]
