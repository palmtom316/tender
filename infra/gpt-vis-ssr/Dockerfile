FROM node:20-bookworm-slim

# Install system dependencies for node-canvas + Cairo + CJK fonts.
# fonts-noto-cjk ensures Chinese text renders correctly in generated charts.
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-noto-cjk \
        libcairo2 \
        libpango-1.0-0 \
        libjpeg62-turbo \
        libgif7 \
        librsvg2-2 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --omit=dev

COPY server.js ./

EXPOSE 7102

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -fsS http://127.0.0.1:7102/health || exit 1

CMD ["node", "server.js"]
