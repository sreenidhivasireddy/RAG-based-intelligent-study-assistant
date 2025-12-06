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

## API Endpoint
The frontend uses `API_BASE_URL = http://localhost:8000/api/v1` (see `src/api.ts`).
If your backend runs elsewhere, update `API_BASE_URL` accordingly.

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
- For production, remember to set the correct API URL before building.

