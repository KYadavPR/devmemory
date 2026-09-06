# DevMemory dashboard — front end

Vite + React + TypeScript. Dependency-free at runtime (no chart library — the
charts are hand-rolled SVG).

## Develop

```bash
cd src/devmemory/web/frontend
npm install
# in another shell: devmemory serve   (the API on :8000)
npm run dev            # http://localhost:5173, proxies /api → :8000
```

## Build

```bash
npm run build          # type-checks, then emits to ../static/
```

`../static/` (`src/devmemory/web/static/`) is **committed** — the Python wheel
ships it, so `devmemory serve` never needs Node. Rebuild and commit it whenever
you change the front end. FastAPI serves `/` → `static/index.html` and
`/static/*` → the hashed assets (see `src/devmemory/api/app.py`).

## Layout

- `src/api/` — typed client (`types.ts` mirrors `devmemory/api/schemas.py`) and
  TanStack Query hooks
- `src/theme/` — design tokens (`theme.css`), component styles (`components.css`),
  `ThemeProvider` (system / light / dark, `?theme=` override)
- `src/components/` — shell, command palette (⌘K), primitives, charts
- `src/routes/` — one file per page; hash-routed
