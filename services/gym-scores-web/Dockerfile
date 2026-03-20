FROM node:22-alpine AS builder

WORKDIR /app

# Build-time API URL (Next.js inlines NEXT_PUBLIC_* at build). Override with --build-arg if needed.
ARG NEXT_PUBLIC_API_URL=https://gym-scores-api-617613197143.us-central1.run.app
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

# Install deps
COPY package.json package-lock.json* ./
RUN npm install

# Build
COPY . .
RUN mkdir -p public
RUN mkdir -p public && npm run build

FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    PORT=8080 \
    HOSTNAME=0.0.0.0

# Copy runtime assets only
COPY --from=builder /app/package.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.* ./

EXPOSE 8080

CMD ["node", "node_modules/next/dist/bin/next", "start", "-p", "8080"]