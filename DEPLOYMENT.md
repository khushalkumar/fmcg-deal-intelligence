# Deployment Guide: Google Cloud Run + GitHub Pages

This guide walks through deploying the FMCG Deal Intelligence Pipeline as a fully serverless, automated system using Google Cloud Platform.

## Architecture Overview

```
Cloud Scheduler (every 15 days)
  └──▶ Cloud Run Job (boots Docker container)
         └──▶ python main.py --source live
               └──▶ Generates newsletter files
                      └──▶ git push → GitHub Pages auto-deploys dashboard
```

**Total monthly cost: ~$0.01** (OpenAI API tokens only. GCP free tier covers compute.)

---

## Prerequisites

- [Google Cloud SDK (gcloud CLI)](https://cloud.google.com/sdk/docs/install) installed
- A GCP project with billing enabled
- Your GitHub repo: `https://github.com/khushalkumar/fmcg-deal-intelligence`
- Your OpenAI API key

---

## Step 1: Enable GitHub Pages (Frontend)

1. Go to **[github.com/khushalkumar/fmcg-deal-intelligence/settings/pages](https://github.com/khushalkumar/fmcg-deal-intelligence/settings/pages)**
2. Under **Source**, select **"Deploy from a branch"**
3. Set branch to **`main`** and folder to **`/dashboard`** *(Note: GitHub Pages only supports root `/` or `/docs`. If `/dashboard` is not available, see Step 1b below.)*

### Step 1b: If GitHub Pages doesn't support `/dashboard` directly

Rename your `dashboard/` folder to `docs/`:
```bash
git mv dashboard docs
git commit -m "rename dashboard to docs for GitHub Pages"
git push
```
Then select **`/docs`** in GitHub Pages settings.

Your dashboard will be live at: `https://khushalkumar.github.io/fmcg-deal-intelligence`

---

## Step 2: Set Up GCP Project

```bash
# Set your project ID (replace with your actual project ID)
export PROJECT_ID="your-gcp-project-id"

gcloud config set project $PROJECT_ID

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudscheduler.googleapis.com
```

---

## Step 3: Create Artifact Registry Repository

This is where your Docker image will be stored.

```bash
gcloud artifacts repositories create fmcg-pipeline \
  --repository-format=docker \
  --location=asia-south1 \
  --description="FMCG Deal Intelligence Pipeline"
```

---

## Step 4: Build and Push Docker Image

```bash
# Configure Docker to authenticate with GCP
gcloud auth configure-docker asia-south1-docker.pkg.dev

# Build the image
docker build -t asia-south1-docker.pkg.dev/$PROJECT_ID/fmcg-pipeline/fmcg-intel:latest .

# Push to Artifact Registry
docker push asia-south1-docker.pkg.dev/$PROJECT_ID/fmcg-pipeline/fmcg-intel:latest
```

---

## Step 5: Create Cloud Run Job

```bash
gcloud run jobs create fmcg-pipeline-job \
  --image=asia-south1-docker.pkg.dev/$PROJECT_ID/fmcg-pipeline/fmcg-intel:latest \
  --region=asia-south1 \
  --memory=512Mi \
  --cpu=1 \
  --max-retries=1 \
  --task-timeout=600s \
  --set-env-vars="OPENAI_API_KEY=sk-your-key-here"
```

> **Security Tip:** For production, use [GCP Secret Manager](https://cloud.google.com/secret-manager) instead of `--set-env-vars` to store your API key securely.

---

## Step 6: Test the Job Manually

```bash
gcloud run jobs execute fmcg-pipeline-job --region=asia-south1
```

Check the logs:
```bash
gcloud run jobs executions list --job=fmcg-pipeline-job --region=asia-south1
```

---

## Step 7: Schedule with Cloud Scheduler (Every 15 Days)

```bash
gcloud scheduler jobs create http fmcg-bimonthly-trigger \
  --location=asia-south1 \
  --schedule="0 9 1,15 * *" \
  --uri="https://asia-south1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/fmcg-pipeline-job:run" \
  --http-method=POST \
  --oauth-service-account-email="$PROJECT_ID@appspot.gserviceaccount.com" \
  --time-zone="Asia/Kolkata"
```

The cron expression `0 9 1,15 * *` means: **Run at 9:00 AM IST on the 1st and 15th of every month.**

---

## Step 8: Verify Everything

1. **Dashboard Live?** → Visit `https://khushalkumar.github.io/fmcg-deal-intelligence`
2. **Cloud Run Job working?** → `gcloud run jobs executions list --job=fmcg-pipeline-job --region=asia-south1`
3. **Scheduler configured?** → `gcloud scheduler jobs list --location=asia-south1`

---

## Updating the Pipeline

When you make code changes:

```bash
# Rebuild and push updated Docker image
docker build -t asia-south1-docker.pkg.dev/$PROJECT_ID/fmcg-pipeline/fmcg-intel:latest .
docker push asia-south1-docker.pkg.dev/$PROJECT_ID/fmcg-pipeline/fmcg-intel:latest

# Update the Cloud Run Job to use the new image
gcloud run jobs update fmcg-pipeline-job \
  --image=asia-south1-docker.pkg.dev/$PROJECT_ID/fmcg-pipeline/fmcg-intel:latest \
  --region=asia-south1
```

---

## Cost Summary

| Component | Monthly Cost |
|---|---|
| Cloud Run Job (~60s every 15 days) | $0.00 (free tier) |
| Cloud Scheduler (2 invocations/mo) | $0.00 (3 free jobs) |
| Artifact Registry (Docker image) | $0.00 (free tier: 500MB) |
| GitHub Pages (static hosting) | $0.00 |
| OpenAI API (embeddings + GPT) | ~$0.01 |
| **Total** | **~$0.01/month** |
