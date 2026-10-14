# Study Buddy

> A web application that students — from **primary level** all the way to the later **university** stages — can use in place of a tutor to learn more about a subject.

Study Buddy is an AI tutor. A student **types their problem or uploads a photo/PDF** of their homework, picks their level, and receives a **step-by-step, level-adapted explanation** instead of a bare answer. They can then **ask follow-up questions**, keep a **history** of everything they've solved, and **copy or download** the results.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white)
![CI](https://github.com/fatmilsaidi6-cmyk/student-tutor/actions/workflows/ci.yml/badge.svg)

---

## Table of contents

- [Features](#features)
- [How it works](#how-it-works)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Running in VS Code](#running-in-vs-code)
- [Testing](#testing)
- [Deployment](#deployment)
- [Security & privacy](#security--privacy)
- [License](#license)

## Features

- **Level-adapted tutoring** — explanations tuned for Primary, Middle, High School, or University students (vocabulary, rigour, and depth all change).
- **Type it or snap it** — the typed problem is the primary input; a photo or PDF is *optional*. Several pages can be added at once.
- **Socratic method** — the tutor restates the problem, works step by step, explains the reasoning, and asks guiding questions rather than dumping the final answer.
- **Follow-up chat** — after the first explanation the student can keep asking questions about the same homework.
- **Real math rendering** — equations are rendered with KaTeX.
- **Study history** — every solved problem is saved in the browser and can be reopened or deleted.
- **Copy / download** — export the explanation and discussion as Markdown.
- **Dark mode** — plus remembered level, engine, and theme preferences.
- **Private-first** — runs fully offline with a local model, with an optional cloud fallback for harder/vision tasks.

## How it works

**1. Reading the homework (`backend/app/extract.py`)**

Uploaded files go through a best-effort, auto-falling-back pipeline:

1. **PDFs with a text layer** are read directly with PyMuPDF.
2. **Images / scanned pages** are tried with **cloud vision** (if an OpenRouter key is configured).
3. Anything still unread falls back to **local Tesseract OCR**.

Typed text is always included, so a file is never required.

**2. Choosing an engine (`backend/app/ai.py`)**

Three modes are available per request:

| Engine  | Behaviour |
| ------- | --------- |
| `local` | Always uses the local Ollama model (private, offline). |
| `cloud` | Always uses OpenRouter (best quality/vision; requires a key). |
| `auto`  | Uses the cloud when a key is set, otherwise the local model — falling back to local if the cloud call fails. |

**3. Tutoring (`backend/app/prompts.py`)**

The prompts define the level-specific voice and a six-point tutoring method (restate → guide → question → full solution only if asked → flag unreadable parts → stay accurate).

## Tech stack

**Backend** — FastAPI, Uvicorn, httpx, PyMuPDF, pytesseract, Pillow, python-dotenv.

**Frontend** — React 19 + Vite, react-markdown, remark-math + rehype-katex (KaTeX), oxlint.

**Models** — any [Ollama](https://ollama.com) model locally, and/or [OpenRouter](https://openrouter.ai) in the cloud.

## Project structure

```
student-tutor/
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI app: /api/health, /api/explain, /api/followup + static hosting
│   │   ├── ai.py          # local (Ollama) + cloud (OpenRouter) backends and routing
│   │   ├── config.py      # environment-based settings
│   │   ├── extract.py     # PDF text layer -> cloud vision -> local OCR
│   │   ├── rate_limit.py  # per-IP rate limiting middleware
│   │   └── prompts.py     # level-adapted Socratic tutoring prompts
│   ├── tests/             # pytest suite (API + extraction)
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # main UI
│   │   ├── components/Markdown.jsx  # markdown + KaTeX renderer
│   │   └── lib/                 # api.js, storage.js
│   └── package.json
├── Dockerfile                   # single-image production build
├── .github/workflows/ci.yml     # tests + lint + build on push/PR
├── PRIVACY.md                   # data handling & child-safety notes
├── .vscode/                     # launch + tasks for debugging/running
└── student-tutor.code-workspace
```

## Getting started

### Prerequisites

- **Python 3.10+**
- **Node.js 20+**
- **[Ollama](https://ollama.com/download)** running locally, with at least one model pulled:
  ```bash
  ollama pull qwen2.5:3b-instruct-q4_K_M   # small & fast on CPU
  ```
- **Tesseract OCR** (only needed for local image OCR):
  ```bash
  # Debian/Ubuntu
  sudo apt install tesseract-ocr
  # macOS
  brew install tesseract
  ```

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit OLLAMA_MODEL to the model you pulled
uvicorn app.main:app --reload --port 8000
```

### Frontend (development)

In a second terminal, with the backend running:

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173  (proxies /api -> :8000)
```

### Production (single server)

Build the frontend and let FastAPI serve everything from one port:

```bash
cd frontend && npm run build
cd ../backend && uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open **http://localhost:8000** — the UI and the API are served by the same process.

> GPU not required: a small quantized model runs on CPU, though answers can take a minute or two. Raise `OLLAMA_TIMEOUT` if needed.

## Configuration

Copy `backend/.env.example` to `backend/.env`:

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `OPENROUTER_API_KEY` | *(empty)* | Enables the cloud engine and cloud vision. Leave blank to run fully offline. |
| `OPENROUTER_MODEL` | `openai/gpt-4o-mini` | Cloud text model. |
| `OPENROUTER_VISION_MODEL` | `openai/gpt-4o-mini` | Cloud model used to read photos/scans. |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Local Ollama server. |
| `OLLAMA_MODEL` | `Qwen-Hermes:latest` | Local model (set this to whatever you pulled). |
| `OLLAMA_TIMEOUT` | `600` | Seconds to wait for a local answer. |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated browser origins allowed to call the API. Only needed for the separate dev frontend; the single-server build is same-origin. |
| `RATE_LIMIT_PER_MINUTE` | `30` | Max AI requests per client IP per minute (`0` disables). |
| `API_KEY` | *(empty)* | When set, the AI endpoints require this key (`X-API-Key` header or `Authorization: Bearer`). The web UI prompts for it and remembers it in the browser. |
| `MAX_IMAGE_PIXELS` | `40000000` | Reject images above this pixel count (decompression-bomb guard). |
| `MAX_PDF_PAGES` | `20` | Reject PDFs with more pages than this. |

## API reference

| Method | Path | Body | Returns |
| ------ | ---- | ---- | ------- |
| `GET`  | `/api/health` | — | status, active models, whether cloud is enabled |
| `POST` | `/api/explain` | multipart: `text`, `files[]`, `level`, `subject`, `question`, `engine` | `explanation`, `extracted_text`, `read_method`, `engine_used`, … |
| `POST` | `/api/followup` | JSON: `context`, `messages[]`, `level`, `subject`, `engine` | `answer`, `engine_used` |

`level` ∈ `primary · middle · high · university`; `engine` ∈ `auto · local · cloud`.

The two AI endpoints are rate-limited per client IP (default 30 requests/minute, see `RATE_LIMIT_PER_MINUTE`). Exceeding it returns `429 Too Many Requests` with a `Retry-After` header.

When `API_KEY` is set, both AI endpoints require it; send `X-API-Key: <key>` or `Authorization: Bearer <key>`. Missing/invalid keys get `401`. `/api/health` reports whether auth is required via `auth_required`.

```bash
curl -X POST http://localhost:8000/api/explain \
  -H "X-API-Key: $API_KEY" \
  -F "text=Solve 2x + 3 = 11 and explain each step." \
  -F "level=middle" -F "subject=Maths" -F "engine=local"
```

Omit the `-H` line when `API_KEY` is unset.

## Running in VS Code

Open **`student-tutor.code-workspace`**. The included configs let you start everything from the editor:

- **F5 → “App: single server (production)”** — builds the frontend and runs the API + UI on `:8000`.
- **F5 → “Full stack (backend + frontend)”** — dev mode: FastAPI on `:8000` and Vite on `:5173`.
- **Terminal → Run Task** — `app: build + run (single server)`, `backend: run`, `frontend: dev`, `frontend: lint`, and more.

## Testing

The backend ships with a [pytest](https://pytest.org) suite covering the API
validation and error paths, rate limiting, and the PDF/OCR extraction pipeline:

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-dev.txt   # installs pytest on top of the app deps
pytest
```

The image-OCR test is skipped automatically when `tesseract` isn't installed.
The frontend is checked with `npm run lint` and `npm run build`. All three run
in CI on every push and pull request (`.github/workflows/ci.yml`).

## Deployment

The app is a single container: a Node stage builds the React UI, and a Python
stage installs the backend (with Tesseract) and serves both the API and the
built site from one port.

```bash
docker build -t study-buddy .
docker run --rm -p 8000:8000 \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
  -e OLLAMA_MODEL=qwen2.5:3b-instruct-q4_K_M \
  study-buddy
```

Then open **http://localhost:8000**.

To use the cloud engine instead of a local model, pass your key and pick a model:

```bash
docker run --rm -p 8000:8000 -e OPENROUTER_API_KEY=sk-or-... study-buddy
```

Notes for hosting:

- Set `PORT` to change the listen port (default `8000`); the image already binds
  to `0.0.0.0` and exposes a `/api/health` health check.
- Serve it behind HTTPS/a reverse proxy and set `CORS_ORIGINS` only if you host
  the frontend on a different origin.
- The built-in rate limiter is per-process; for multiple replicas add a limiter
  at the proxy as well.

## Security & privacy

Study Buddy runs **private by default**: with the local engine, homework never
leaves the machine, and there is no server-side storage or accounts.

- **Access control** — set `API_KEY` to require a shared code on the AI
  endpoints (`X-API-Key` / `Authorization: Bearer`). The UI prompts for it and
  remembers it locally.
- **Abuse protection** — per-IP rate limiting on the AI endpoints.
- **Untrusted uploads** — caps on file size/count, image pixels
  (decompression-bomb guard), and PDF pages; PDFs are read in memory only.
- **Cloud mode** sends the homework text/image to OpenRouter and its model
  provider. Use local mode if content must not leave your infrastructure.

See **[PRIVACY.md](PRIVACY.md)** for the full data-handling notes and guidance
for deploying to children (consent, COPPA/GDPR-K, avoiding identifiable uploads).

## License

No license has been added yet. Until one is chosen, all rights are reserved by the author.
