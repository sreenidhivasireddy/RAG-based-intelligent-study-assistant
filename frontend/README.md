# RAG Frontend

React + Vite web UI for the RAG-based Intelligent Study Assistant.

## Prerequisites
- Node.js 18+ (recommended LTS)
- pnpm / npm / yarn (examples use `npm`)

## Install
```bash
cd frontend
npm install
```

## Development
```bash
npm run dev
```
The dev server defaults to `http://localhost:5173`.

## Build
```bash
npm run build
```
Output will be generated in `dist/`.

## Lint
```bash
npm run lint
```

## Environment Variables
Create `frontend/.env` for local development if you want to override the defaults:

```bash
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_WS_BASE_URL=ws://localhost:8000/api/v1
VITE_HEALTH_URL=http://localhost:8000/health
```

Defaults are local-friendly, so `frontend/.env` is optional for local work.

For deployment, set the same variables in your hosting platform:
- `VITE_API_BASE_URL=https://your-backend-domain/api/v1`
- `VITE_WS_BASE_URL=wss://your-backend-domain/api/v1`
- `VITE_HEALTH_URL=https://your-backend-domain/health`

## Key Features
- Chat UI that calls the real search API (no mocks).
- Displays source document names in results.
- User tip near the input to encourage concise, precise queries.
- Highlights from the backend are rendered with safe HTML.

## Project Structure (major)
```
frontend/
  src/
    api.ts               # HTTP client for search & upload
    types.ts             # Shared TypeScript types
    pages/
      Chat.tsx           # Chat experience with sources accordion
      KnowledgeBase.tsx  # Upload and document management page
    components/
      Layout.tsx         # Basic layout shell
  package.json           # Scripts: dev, build, lint, preview
  tailwind.config.js     # Tailwind setup
  vite.config.ts         # Vite config
```

## Notes
- Backend must be running and reachable at the configured API base URL.
- For production, set the `VITE_*` variables before building.

