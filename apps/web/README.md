# Provok web

Next.js 16 (App Router, TypeScript strict, Tailwind v4, Cache Components) frontend for Provok.
See the repo root `README.md` for the full stack.

```bash
cp .env.example .env.local
npm install
npm run dev          # http://localhost:3000 — API calls are proxied to API_INTERNAL_URL
npm run lint && npm run typecheck && npm run build
```

Design system: "The Arena" (PROVOK_BUILD_SPEC.md §10) — tokens in `src/app/globals.css`.
