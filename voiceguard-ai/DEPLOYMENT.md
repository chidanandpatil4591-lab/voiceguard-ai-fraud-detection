# Deploy VoiceGuard AI

The app has a React frontend and FastAPI backend. Deploy the backend first, then provide its public API URL to the frontend.

## Backend

Deploy the `backend` directory using its included `Dockerfile` on Render, Railway, Fly.io, or another Docker host.

Set `CORS_ORIGINS` to the exact frontend URL, for example `https://voiceguard-ai.vercel.app`. For multiple frontend URLs, use comma-separated values. The backend host must support WebSocket upgrades for `/api/realtime`; configure the proxy/load balancer to forward that path without buffering. Verify `https://YOUR-BACKEND/api/health` after deployment.

## Frontend

Deploy the `frontend` directory as a static Vite site on Vercel, Netlify, or Cloudflare Pages:

- Build command: `npm run build`
- Publish directory: `dist`
- Environment variable: `VITE_API_URL=https://YOUR-BACKEND/api`

Redeploy the frontend after adding `VITE_API_URL`. It will use that endpoint for uploads, history, contextual risk checks, and convert its `https` scheme to `wss` for live capture.

## Local development

No variables are required locally. The frontend defaults to `http://127.0.0.1:8000/api`, and the backend allows both standard Vite local origins.

For local live capture, use `http://localhost:5173` or `http://127.0.0.1:5173` in a browser that grants microphone permission. HTTPS is required by browsers for non-localhost deployments.
