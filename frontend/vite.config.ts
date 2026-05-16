import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // HMR host: when accessing the dev server via a non-localhost name
  // (e.g. http://UZASSETS006:5173 from another machine on the LAN),
  // Vite must advertise that host for the HMR websocket to connect.
  const hmrHost     = env.VITE_HMR_HOST     || "localhost";
  // When Vite is behind nginx (single-origin setup), HMR connects to nginx
  // on 443/80 (NOT 5173 which is internal-only). Set VITE_HMR_PROTOCOL=wss
  // and VITE_HMR_CLIENT_PORT=443 in .env.uzassets006 for that scenario.
  const hmrProtocol = (env.VITE_HMR_PROTOCOL as "ws" | "wss" | undefined) || "ws";
  const hmrClientPort = parseInt(env.VITE_HMR_CLIENT_PORT || "5173", 10);

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    server: {
      host: "0.0.0.0",
      port: 5173,
      strictPort: true,
      // Vite ≥ 5.x rejects requests for non-localhost Host headers by default
      // (DNS-rebinding mitigation). Inside docker-compose, nginx proxies to
      // `http://frontend:5173/` with `Host: frontend` — that's not localhost,
      // so Vite returns 403. Easiest: allow all hosts, since the dev port is
      // not publicly exposed (only nginx-on-443 is reachable from outside).
      allowedHosts: true,
      // Windows + Docker Desktop: native file events don't propagate over the bind mount,
      // so Vite needs polling to detect file changes.
      watch: {
        usePolling: true,
        interval: 500,
      },
      hmr: {
        protocol:   hmrProtocol,
        host:       hmrHost,
        // The port Vite tells the BROWSER to connect to. When behind nginx,
        // this is the public TLS port (443). Server-side, Vite still listens
        // on 5173 inside the container.
        clientPort: hmrClientPort,
        port:       5173,
      },
      // Vite dev-server proxy: ONLY enabled when running raw Vite WITHOUT
      // nginx in front (e.g. local dev hitting http://localhost:5173).
      // In single-origin mode (everything goes through nginx on :443),
      // the browser sends /api/* directly to nginx → backend, and Vite
      // must NOT intercept those requests — otherwise it tries to proxy
      // them itself from inside the container to a host that doesn't exist.
      //
      // To opt INTO the proxy, set VITE_API_BASE_URL in .env to a non-empty
      // URL (e.g. VITE_API_BASE_URL=http://backend:8000).
      proxy: (env.VITE_API_BASE_URL && env.VITE_API_BASE_URL.trim() !== "")
        ? {
            "/api": {
              target: env.VITE_API_BASE_URL,
              changeOrigin: true,
              rewrite: (p) => p.replace(/^\/api/, ""),
            },
          }
        : undefined,
    },
    build: {
      outDir: "dist",
      sourcemap: mode !== "production",
      target: "es2022",
    },
  };
});
