# Jainune

Matrimonial and relationship platform for the Jain community.

## Launch status

Public release is blocked pending the supported mobile SDK/native migration, completed store billing, dependency remediation, signing and device/provider acceptance. See [launch readiness](docs/LAUNCH_READINESS.md), [Android/iOS layout plan](docs/ANDROID_IOS_LAYOUT.md), and [validation record](docs/VALIDATION.md). Historical audit verdicts do not replace these release gates.

## Structure

- `backend/`: FastAPI backend, asyncpg, Redis, PostgreSQL (PostGIS + pgvector)
- `mobile/`: Expo React Native client
- `deploy/`: Docker, k8s, CI/CD, infrastructure configurations
- `mds/`: System specifications, architecture, and roadmap documents
