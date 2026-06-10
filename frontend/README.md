# MediaForge Web UI

Minimal local web interface for running the MediaForge pipeline:

`create session → discover → parse → match TMDB → create plan → inspect operations`

## Setup

```bash
cd frontend
npm install
cp .env.example .env
```

## Development

Start the backend from the repository root:

```bash
uvicorn backend.app.main:app --reload
```

Start the frontend dev server:

```bash
npm run dev
```

Open `http://localhost:5173`.

## Build

```bash
npm run build
npm run preview
```

## Configuration

Set the backend API URL in `frontend/.env`:

```bash
VITE_API_BASE_URL=http://localhost:8000
```

Do not commit `frontend/.env`.
