FROM node:22-slim AS base

# Install runtime/build deps used by the admin image build.
RUN apt-get update && apt-get install -y bash curl graphicsmagick libvips-dev build-essential

# All deps stage
FROM base AS deps
WORKDIR /app
ADD admin/package.json admin/package-lock.json ./
RUN npm ci

# Production only deps stage
FROM base AS production-deps
WORKDIR /app
ADD admin/package.json admin/package-lock.json ./
RUN npm ci --omit=dev

# Build stage
FROM base AS build
WORKDIR /app
COPY --from=deps /app/node_modules /app/node_modules
ADD admin/ ./
RUN node ace build

# Production stage
FROM base
ARG VERSION=dev
ARG BUILD_DATE
ARG VCS_REF

# Labels
LABEL org.opencontainers.image.title="Project J.A.R.V.I.S" \
      org.opencontainers.image.description="The Project J.A.R.V.I.S official Docker image" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.vendor="Ambidiosidad" \
      org.opencontainers.image.documentation="https://github.com/Ambidiosidad/jarvis/blob/main/README.md" \
      org.opencontainers.image.source="https://github.com/Ambidiosidad/jarvis" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV NODE_ENV=production
WORKDIR /app
COPY --from=production-deps /app/node_modules /app/node_modules
COPY --from=build /app/build /app
# Copy root package.json for version info
COPY package.json /app/version.json
COPY admin/docs /app/docs
COPY README.md /app/README.md
EXPOSE 8080
CMD ["node", "./bin/server.js"]
