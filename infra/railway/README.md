# Railway Deployment

Deploy both services (web + api) on Railway.

## Setup

1. Create a new Railway project
2. Add two services from the same repo:

### Web Service (Next.js)
- **Root Directory**: `apps/web`
- **Build Command**: `pnpm install && pnpm build`
- **Start Command**: `pnpm start`
- **Port**: `3000`

### API Service (FastAPI)
- **Root Directory**: `services/api`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`

## Environment Variables

Set these on the API service:

| Variable | Value |
|----------|-------|
| `B2_APPLICATION_KEY_ID` | Your B2 key ID |
| `B2_APPLICATION_KEY` | Your B2 key |
| `B2_BUCKET_NAME` | Your bucket name |
| `B2_REGION` | Your B2 bucket region |
| `B2_PUBLIC_URL_BASE` | Optional public bucket URL base for direct object links |
| `API_CORS_ORIGINS` | Your web service URL (e.g., `https://web-production-xxx.up.railway.app`) |

During the migration to standardized B2 names, the API still accepts
`B2_KEY_ID` as a fallback for `B2_APPLICATION_KEY_ID`, ignores leftover
`B2_ENDPOINT`, and accepts `B2_PUBLIC_URL` as a fallback for
`B2_PUBLIC_URL_BASE`. For rolling deploys, set both old and new variables,
deploy the new API, then remove the old variables after every old API
instance has exited. Prefer the standardized names above for all new
Railway variables.

Set this on the Web service:

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_API_URL` | Your API service URL (e.g., `https://api-production-xxx.up.railway.app`) |
