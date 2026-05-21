FROM node:20-alpine AS deps

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@9.15.3 --activate

COPY package.json pnpm-lock.yaml ./
RUN pnpm config set fetch-retries 8 \
    && pnpm config set fetch-retry-factor 2 \
    && pnpm config set fetch-retry-mintimeout 10000 \
    && pnpm config set fetch-retry-maxtimeout 180000 \
    && pnpm config set network-timeout 600000 \
    && pnpm install --frozen-lockfile --reporter append-only

FROM node:20-alpine AS builder

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@9.15.3 --activate

ARG NEXT_PUBLIC_ENV=development
ARG NEXT_PUBLIC_API_BASE_URI=http://localhost:8000
ARG NEXT_PUBLIC_ENABLE_MOCK_UI=false
ARG NEXT_PUBLIC_MOCK_ROLE=TENANT_ADMIN

ENV NEXT_PUBLIC_ENV=${NEXT_PUBLIC_ENV} \
    NEXT_PUBLIC_API_BASE_URI=${NEXT_PUBLIC_API_BASE_URI} \
    NEXT_PUBLIC_ENABLE_MOCK_UI=${NEXT_PUBLIC_ENABLE_MOCK_UI} \
    NEXT_PUBLIC_MOCK_ROLE=${NEXT_PUBLIC_MOCK_ROLE}

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN pnpm build

FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

RUN corepack enable && corepack prepare pnpm@9.15.3 --activate

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.ts ./next.config.ts

EXPOSE 3000

CMD ["pnpm", "exec", "next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
