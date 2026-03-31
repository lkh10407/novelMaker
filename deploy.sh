#!/usr/bin/env bash
# NovelMaker — Google Cloud Run 자동 배포 스크립트
# 사용법: bash deploy.sh
set -euo pipefail

# ─── 설정 ───
PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="asia-northeast3"          # 서울
SERVICE_NAME="novelmaker"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-2.5-flash}"

# gcloud 경로 (brew 설치 시)
set +u
if [ -f "$(brew --prefix 2>/dev/null)/share/google-cloud-sdk/path.zsh.inc" ]; then
  source "$(brew --prefix)/share/google-cloud-sdk/path.zsh.inc"
fi
set -u

# ─── 사전 검사 ───
if ! command -v gcloud &>/dev/null; then
  echo "❌ gcloud CLI가 없습니다. brew install --cask google-cloud-sdk"
  exit 1
fi

# ─── 1. 로그인 확인 ───
ACCOUNT=$(gcloud auth list --filter="status:ACTIVE" --format="value(account)" 2>/dev/null || true)
if [ -z "$ACCOUNT" ]; then
  echo "🔐 Google Cloud 로그인이 필요합니다..."
  gcloud auth login
fi
echo "✅ 로그인: $(gcloud auth list --filter='status:ACTIVE' --format='value(account)')"

# ─── 2. 프로젝트 선택 ───
if [ -z "$PROJECT_ID" ]; then
  CURRENT=$(gcloud config get-value project 2>/dev/null || true)
  if [ -n "$CURRENT" ] && [ "$CURRENT" != "(unset)" ]; then
    echo "📁 현재 프로젝트: $CURRENT"
    read -p "   이 프로젝트를 사용할까요? (Y/n): " USE_CURRENT
    if [[ "${USE_CURRENT:-Y}" =~ ^[Yy]$ ]]; then
      PROJECT_ID="$CURRENT"
    fi
  fi
  if [ -z "$PROJECT_ID" ]; then
    echo "📋 프로젝트 목록:"
    gcloud projects list --format="table(projectId, name)" 2>/dev/null
    read -p "🔹 프로젝트 ID 입력: " PROJECT_ID
  fi
fi
gcloud config set project "$PROJECT_ID"
echo "✅ 프로젝트: $PROJECT_ID"

# ─── 3. 필수 API 활성화 ───
echo "🔧 필수 API 활성화 중..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com --quiet

# ─── 4. GOOGLE_API_KEY 확인 ───
GOOGLE_API_KEY="${GOOGLE_API_KEY:-}"
if [ -z "$GOOGLE_API_KEY" ]; then
  # .env 파일에서 읽기
  if [ -f .env ]; then
    GOOGLE_API_KEY=$(grep -E '^GOOGLE_API_KEY=' .env | cut -d'=' -f2- | tr -d '"' | tr -d "'")
  fi
  if [ -z "$GOOGLE_API_KEY" ]; then
    read -p "🔑 Gemini API Key 입력: " GOOGLE_API_KEY
  fi
fi

# ─── 5. Cloud Run 배포 ───
echo ""
echo "🚀 Cloud Run 배포 시작..."
echo "   서비스: $SERVICE_NAME"
echo "   리전: $REGION"
echo ""

gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "GOOGLE_API_KEY=$GOOGLE_API_KEY,GEMINI_MODEL=$GEMINI_MODEL" \
  --memory 2Gi \
  --cpu 2 \
  --timeout 900 \
  --min-instances 0 \
  --max-instances 2 \
  --quiet

# ─── 6. URL 출력 ───
URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format="value(status.url)")
echo ""
echo "════════════════════════════════════════"
echo "✅ 배포 완료!"
echo "🌐 URL: $URL"
echo "════════════════════════════════════════"
