#!/usr/bin/env bash
# Render build script — installs Python deps + builds frontend
set -o errexit

pip install -r requirements.txt

# Build frontend
cd web
npm install
npm run build
cd ..
