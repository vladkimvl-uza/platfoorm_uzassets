FROM node:20-alpine

WORKDIR /app

# Install dependencies first (layer cache)
COPY package*.json ./
RUN npm install --no-audit --no-fund

# Copy source
COPY . .

# Vite dev server on 5174 (avoid clash with main frontend on 5173)
EXPOSE 5174

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5174", "--strictPort"]
