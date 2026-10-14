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
- [Authentication](#authentication)
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
- **Optional sign-in** — for public deployments, gate the app behind Google/GitHub OAuth; history still stays in the browser.

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

**Backend** — FastAPI, Uvicorn, httpx, PyMuPDF, pytesseract, Pillow, python-dotenv; OAuth via httpx with a signed session cookie (itsdangerous).

**Frontend** — React 19 + Vite, react-markdown, remark-math + rehype-katex (KaTeX), oxlint.

**Models** — any [Ollama](https://ollama.com) model locally, and/or [OpenRouter](https://openrouter.ai) in the cloud.

**Auth** — optional Google / GitHub sign-in (no database; identity in a signed cookie).

## Project structure

```
student-tutor/
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI app: /api/health, /api/explain, /api/followup + static hosting
│   │   ├── ai.py          # local (Ollama) + cloud (OpenRouter) backends and routing
│   │   ├── config.py      # environment-based settings
│   │   ├── extract.py     # PDF text layer -> cloud vision -> local OCR
│   │   ├── auth.py        # Google/GitHub OAuth, session + access gate
│   │   ├── rate_limit.py  # per-user/IP rate limiting middleware
│   │   └── prompts.py     # level-adapted Socratic tutoring prompts
│   ├── tests/             # pytest suite (API, auth, extraction, rate limit)
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # main UI
│   │   ├── components/Login.jsx     # sign-in screen
│   │   ├── components/Markdown.jsx  # markdown + KaTeX renderer
│   │   └── lib/                 # api.js, storage.js
│   └── package.json
├── Dockerfile                   # single-image production build
├── fly.toml                     # Fly.io deployment config
├── .github/workflows/ci.yml     # tests + lint + build + docker on push/PR
├── PRIVACY.md                   # data handling & child-safety notes
├── LICENSE                      # MIT
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
| `RATE_LIMIT_PER_MINUTE` | `30` | Max AI requests per user/IP per minute (`0` disables). |
| `DAILY_QUOTA` | `100` | Max AI requests per user/IP per UTC day (`0` disables). Caps cloud cost. |
| `API_KEY` | *(empty)* | When set, the AI endpoints require this key (`X-API-Key` header or `Authorization: Bearer`). The web UI prompts for it and remembers it in the browser. |
| `MAX_IMAGE_PIXELS` | `40000000` | Reject images above this pixel count (decompression-bomb guard). |
| `MAX_PDF_PAGES` | `20` | Reject PDFs with more pages than this. |
| `SESSION_SECRET` | `dev-insecure-change-me` | Signing key for the session cookie. **Set a long random value in production.** |
| `PUBLIC_BASE_URL` | *(empty)* | Public URL of the deployment (e.g. `https://study-buddy.fly.dev`). Used to build OAuth redirect URIs and to mark the cookie `Secure`. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | *(empty)* | Enable "Sign in with Google". |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | *(empty)* | Enable "Sign in with GitHub". |
| `ALLOWED_EMAILS` | *(empty)* | Optional comma-separated allowlist of emails. Empty = any signed-in user. |
| `TRUST_PROXY` | `false` | Trust `X-Forwarded-For` / `Fly-Client-IP` for the client IP (rate limiting). Set `true` behind a proxy. |

## Authentication

By default the app is open (ideal for local/self-hosted use). To publish it
publicly, enable one or both OAuth providers — when any is configured, the AI
endpoints require a signed-in user, and the UI shows a sign-in screen. No
database is used: the provider profile (name, email, avatar) is stored in a
signed, HTTP-only session cookie, and homework/history stays in the browser.

**1. Create the OAuth apps**

- **Google** — [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
  → *Create credentials* → *OAuth client ID* → *Web application*.
  Authorized redirect URI: `https://<your-domain>/api/auth/callback/google`
- **GitHub** — [GitHub Developer settings](https://github.com/settings/developers)
  → *New OAuth App*. Authorization callback URL:
  `https://<your-domain>/api/auth/callback/github`

For local testing use `http://localhost:8000/api/auth/callback/<provider>`
(the backend derives the redirect URI from the request, or from `PUBLIC_BASE_URL`).

**2. Set the secrets**

```bash
export SESSION_SECRET="$(openssl rand -hex 32)"   # required
export PUBLIC_BASE_URL="https://<your-domain>"
export GOOGLE_CLIENT_ID=...  GOOGLE_CLIENT_SECRET=...
export GITHUB_CLIENT_ID=...  GITHUB_CLIENT_SECRET=...
# optional: restrict who may sign in
export ALLOWED_EMAILS="me@example.com,co-teacher@example.com"
```

On Fly.io, set these with `fly secrets set ...` (see [Deployment](#deployment)).

**3. Restrict access (recommended for children).** Set `ALLOWED_EMAILS` to an
allowlist, or leave it empty to allow any signed-in account. Combine with the
per-user rate limit to cap cost.

## API reference

| Method | Path | Body | Returns |
| ------ | ---- | ---- | ------- |
| `GET`  | `/api/health` | — | status, active models, `auth_required`, `oauth_providers` |
| `GET`  | `/api/auth/me` | — | the signed-in `user` (or `null`) and configured providers |
| `GET`  | `/api/auth/login/{provider}` | — | `302` redirect to the provider |
| `GET`  | `/api/auth/callback/{provider}` | `code`, `state` | sets the session, redirects to `/` |
| `POST` | `/api/auth/logout` | — | clears the session |
| `POST` | `/api/explain` | multipart: `text`, `files[]`, `level`, `subject`, `question`, `engine` | `explanation`, `extracted_text`, `read_method`, `engine_used`, … |
| `POST` | `/api/followup` | JSON: `context`, `messages[]`, `level`, `subject`, `engine` | `answer`, `engine_used` |

`level` ∈ `primary · middle · high · university`; `engine` ∈ `auto · local · cloud`.

The two AI endpoints are limited per signed-in user (or client IP when signed
out): a short-window rate limit (`RATE_LIMIT_PER_MINUTE`, default 30/min) and a
daily quota (`DAILY_QUOTA`, default 100/day, resetting at UTC midnight).
Exceeding either returns `429 Too Many Requests` with a `Retry-After` header.
When the quota is enabled, responses also carry `X-Quota-Limit` and
`X-Quota-Remaining` headers.

**Access control.** When OAuth is configured, the AI endpoints require a
signed-in session. When `API_KEY` is set, they instead (or additionally) accept
that key via `X-API-Key: <key>` or `Authorization: Bearer <key>`. When neither
is configured the app is open. Missing credentials return `401`.

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

- The container has **no local model** — on a host, set `OPENROUTER_API_KEY` to
  use the cloud engine (the default `auto` engine will pick it up), or point
  `OLLAMA_BASE_URL` at an external Ollama server.
- Set `PORT` to change the listen port (default `8000`); the image binds to
  `0.0.0.0` and exposes a `/api/health` health check.
- Serve it behind HTTPS and set `TRUST_PROXY=true` so rate limiting sees the
  real client IP. Set `PUBLIC_BASE_URL` so cookies are `Secure` and OAuth
  redirect URIs are correct.
- The built-in rate limiter is per-process and in-memory; for multiple replicas
  add a limiter at the proxy as well.

### Fly.io

A `fly.toml` is included.

```bash
fly launch --no-deploy          # or edit `app` in fly.toml to a unique name
fly secrets set \
  SESSION_SECRET="$(openssl rand -hex 32)" \
  OPENROUTER_API_KEY=sk-or-... \
  PUBLIC_BASE_URL="https://<app>.fly.dev" \
  GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... \
  GITHUB_CLIENT_ID=... GITHUB_CLIENT_SECRET=...
fly deploy
```

Then add the callback URLs (`https://<app>.fly.dev/api/auth/callback/google`
and `.../github`) to the provider apps you created in
[Authentication](#authentication).

## Security & privacy

Study Buddy runs **private by default**: with the local engine, homework never
leaves the machine, and there is no server-side storage of homework or history.

- **Access control** — enable Google/GitHub OAuth (recommended for public use)
  and/or set `API_KEY`. Sessions are signed HTTP-only cookies; identity (name,
  email, avatar) is the only thing stored, never homework.
- **Abuse & cost protection** — per-user/IP rate limiting **and a daily quota**
  (`DAILY_QUOTA`), plus an optional `ALLOWED_EMAILS` allowlist. The UI shows the
  remaining daily requests.
- **Untrusted uploads** — caps on file size/count, image pixels
  (decompression-bomb guard), and PDF pages; PDFs are read in memory only.
- **Cloud mode** sends the homework text/image to OpenRouter and its model
  provider. Use local mode if content must not leave your infrastructure.

See **[PRIVACY.md](PRIVACY.md)** for the full data-handling notes and guidance
for deploying to children (consent, COPPA/GDPR-K, avoiding identifiable uploads).

## License

Released under the [MIT License](LICENSE).
