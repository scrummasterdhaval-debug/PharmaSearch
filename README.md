# PharmaSearch

Search engine for pharma compliance.

A BM25 index over regulatory documents (21 CFR, EudraLex, ICH, WHO), served as a
container-native HTTP API that runs unchanged on Cloud Run, ECS, App Runner,
Fly or Kubernetes.

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
PORT=8080 .venv/bin/uvicorn app.main:app --port 8080
curl "http://localhost:8080/search?q=audit+trail+review&limit=3"
```

## API

| Endpoint   | Purpose                                                      |
|------------|--------------------------------------------------------------|
| `/search`  | `q` (required), `jurisdiction` (US/EU/ICH/WHO), `limit`       |
| `/healthz` | Liveness — process is up, touches nothing                     |
| `/readyz`  | Readiness — index built, returns document count               |
| `/docs`    | Generated OpenAPI UI                                          |

Configuration is read from the environment: `PORT`, `LOG_LEVEL`,
`PHARMASEARCH_ENV`, `PHARMASEARCH_CORPUS`, `PHARMASEARCH_MAX_LIMIT`.

## Deploy

```bash
docker build -t pharmasearch:latest .
gcloud run services replace deploy/cloudrun.yaml --region europe-west1   # Cloud Run
kubectl apply -f deploy/k8s.yaml                                          # Kubernetes
```

---

## What "vibe coding" is, and how it works in the cloud

**Vibe coding** is the practice of building software by describing the outcome you
want in natural language and letting an AI model produce the code, then steering
it by reaction — you run the result, see how it feels, and say "now add a
jurisdiction filter" rather than writing the filter yourself. The term was coined
by Andrej Karpathy in early 2025 for the mode where you "fully give in to the
vibes" and largely stop reading the diff line by line.

It is genuinely fast. It is also how you end up with a service that passes a demo
and falls over in production, because the model optimises for *looking* right.
The discipline that makes it work is not better prompting — it is **putting the
verification outside the vibe**. You can be loose about how the code gets written
as long as something strict decides whether it is correct.

This repository is a worked example of exactly that split.

### The loose part

The ranking, the API surface, the corpus schema and the snippet logic were all
generated from a one-line intent: *a search engine for pharma compliance*. Nobody
specified BM25 parameters, the dataclass layout or the shape of `SearchResponse`.

### The strict part — the five guardrails

| Guardrail | File | What it catches |
|---|---|---|
| Tests on behaviour, not implementation | `tests/` | 18 tests. One of them caught a real relevance bug during this build. |
| Loud failure over silent fallback | `app/corpus.py` | A malformed corpus refuses to start, instead of answering "no results" to every compliance query. |
| Config from environment | `app/config.py` | Honouring injected `$PORT` is the difference between a container that serves and one the platform kills. |
| Separate liveness from readiness | `app/main.py` | Traffic only arrives after the index is built. |
| Structured logs with request IDs | `app/logging_config.py` | A cloud log viewer parses JSON and little else. |

### Why the cloud raises the stakes

Vibe coding and cloud deployment pull in opposite directions, and the tension is
the whole problem:

- **Cold starts.** Generated code loves lazy, per-request initialisation. Here the
  index is built once in a `lifespan` hook. Rebuilding it per request would be
  invisible locally and ruinous under load.
- **Replicas must agree.** Equal-scoring results are tie-broken by document id, so
  two instances page identically. Non-deterministic ordering is the classic
  vibe-coded bug that only appears once you scale past one container.
- **Unbounded inputs.** `limit` is capped from config. A generated endpoint will
  cheerfully accept `limit=10000000`.
- **Blast radius.** Locally a bad deploy costs you a restart. In a cloud it costs
  you a bill, an incident, and — in a regulated domain like pharma — an audit
  finding. `.github/workflows/ci.yml` runs the tests *and* boots the built image
  and curls it, so nothing reaches a registry that has not served a real request.

### The honest limits

Vibe coding is excellent for the 80% that is scaffolding: HTTP plumbing, config,
containers, manifests, test harnesses. It is unreliable for the part that
actually matters — here, whether BM25 over twelve paraphrased documents is a
defensible way to rank regulatory guidance. It is not, yet. A real PharmaSearch
needs relevance judgements from compliance officers, document versioning against
effective dates, and traceability from an answer back to a citation an auditor
will accept. No amount of vibing produces those; they come from domain experts.

**Use the model for the scaffolding. Keep a human on the part that would get you
a warning letter.**
