#!/bin/bash
# PronoGol Deploy Script
# Runs from repo on VPS: /docker/pronogol-repo/deploy.sh
set -e

echo "📥 Pulling latest code..."
cd /docker/pronogol-repo
git pull origin master

echo "🔨 Updating frontend..."
cp apps/web/Dockerfile /docker/pronogol-web/Dockerfile
cp apps/web/nginx.conf /docker/pronogol-web/nginx.conf
cp apps/web/index.html /docker/pronogol-web/index.html

echo "🔨 Updating backend..."
rm -rf /docker/pronogol/app
cp -r backend/app /docker/pronogol/app
cp backend/requirements.txt /docker/pronogol/requirements.txt
cp backend/Dockerfile /docker/pronogol/Dockerfile

echo "🐳 Rebuilding backend container..."
cd /docker/pronogol
docker build -t pronogol-api:latest .
docker rm -f n8n-pronogol-api-1 2>/dev/null || true
docker run -d \
  --name n8n-pronogol-api-1 \
  --restart unless-stopped \
  -v /docker/pronogol/data:/app/data \
  --network n8n_default \
  pronogol-api:latest

echo "🐳 Rebuilding frontend container..."
cd /docker/pronogol-web
docker build -t pronogol-web:latest .
docker rm -f n8n-pronogol-web-1 2>/dev/null || true
docker run -d \
  --name n8n-pronogol-web-1 \
  --restart unless-stopped \
  --network n8n_default \
  -l "traefik.enable=true" \
  -l "traefik.http.routers.pronogol-web.rule=Host(\`pronogol.app\`)" \
  -l "traefik.http.routers.pronogol-web.tls=true" \
  -l "traefik.http.routers.pronogol-web.tls.certresolver=letsencrypt" \
  -l "traefik.http.services.pronogol-web.loadbalancer.server.port=3000" \
  pronogol-web:latest

echo "✅ Verifying..."
sleep 3
echo "Frontend: $(curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/)"
echo "Backend:  $(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/)"
echo ""
echo "🎉 Deploy complete!"
docker ps --format "table {{.Names}}\t{{.Status}}"
