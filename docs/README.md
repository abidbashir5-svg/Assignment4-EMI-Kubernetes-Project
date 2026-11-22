# Loan EMI Calculator — Milestone 1

Flask + jQuery/Bootstrap + MongoDB implementation of the Milestone 1 requirements.

## Fast local run (Docker Compose)

From this directory:

```bash
docker compose up --build -d
docker compose ps
```

Open `http://localhost:5000`.

Quick endpoint checks:

```bash
curl -i http://localhost:5000/api/health
curl -s http://localhost:5000/api/history
curl -s -X POST http://localhost:5000/api/emi \
  -H 'Content-Type: application/json' \
  -d '{"principal":500000,"rate":12,"months":24}'
```

Stop services while preserving MongoDB data:

```bash
docker compose down
```

To remove the MongoDB data volume as well (destructive):

```bash
docker compose down -v
```

## What is included

- `POST /api/emi`: validates positive inputs, calculates EMI, stores the calculation, and returns totals plus serving container/pod identity.
- `GET /api/history`: returns the newest 10 calculations.
- `GET /api/health`: returns HTTP 200 only when MongoDB responds to a ping; otherwise HTTP 503.
- `MONGO_URL` is read from the environment. No MongoDB host, username, or password is hard-coded in application source.
- `HOSTNAME` is used for the serving pod/container name. Kubernetes deployment should inject `POD_IP` using the Downward API.
- The browser submits the form using jQuery AJAX and updates only the result and history sections.

## Kubernetes note for later milestones

Set `MONGO_URL` in the Kubernetes Deployment to the MongoDB replica-set URI required by the assignment, and inject `POD_IP` using `status.podIP`. The same application image can then be reused.
