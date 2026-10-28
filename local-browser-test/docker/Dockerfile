# chrome-devtools-mcp (stdio) + Debian Chromium, for opencode tests. Headless, throw-away profile (--isolated).
FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends chromium fonts-liberation fonts-noto-color-emoji ca-certificates && rm -rf /var/lib/apt/lists/* \
 && npm i -g chrome-devtools-mcp@1.11.0
ENTRYPOINT ["chrome-devtools-mcp", "--headless", "--isolated", "--executablePath", "/usr/bin/chromium", "--chromeArg=--no-sandbox", "--viewport", "1280x900"]
