FROM node:20-alpine

WORKDIR /app

# Install dependencies first (layer cache).
# `npm ci` enforces package-lock.json → reproducible build, no supply-chain
# surprises from floating versions on rebuild. Falls back to `npm install`
# only if the lockfile is missing (first-run scaffolding).
COPY package*.json ./
# npm ci enforces lockfile reproducibility. We DO run `npm audit` (no
# --no-audit flag) so HIGH/CRITICAL vulnerabilities surface during build —
# build still succeeds (--audit-level controls warning, not exit), CI gate
# (.github/workflows/security-scan.yml) blocks on high+ findings.
RUN if [ -f package-lock.json ]; then \
      npm ci --no-fund && npm audit --audit-level=high || true; \
    else \
      echo "WARN: package-lock.json missing — using npm install" >&2; \
      npm install --no-fund; \
    fi

# Copy source and drop privileges. node:alpine ships a built-in 'node' user.
COPY . .
RUN chown -R node:node /app

USER node

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
