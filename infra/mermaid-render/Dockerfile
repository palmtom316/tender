FROM node:20-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      chromium \
      fonts-noto-cjk \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    PUPPETEER_SKIP_DOWNLOAD=true

WORKDIR /app

RUN npm install -g @mermaid-js/mermaid-cli@11.4.2

COPY server.js ./

EXPOSE 3000

CMD ["node", "server.js"]
