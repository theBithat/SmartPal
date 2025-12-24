#!/bin/bash

# Quick deployment script - updates CSS without full Docker rebuild
echo "🚀 Quick deploying production CSS to 66.94.110.211..."

# Build CSS locally first
echo "📦 Building CSS locally..."
npm run build:css

# Copy compiled CSS to server
echo "📤 Uploading compiled CSS..."
sshpass -p 'amir13579' scp static/css/output.css root@66.94.110.211:/root/trader-bot/static/css/

# Copy updated base.html template
echo "📤 Uploading updated template..."
sshpass -p 'amir13579' scp templates_arena/base.html root@66.94.110.211:/root/trader-bot/templates_arena/

# Restart Flask app (not full rebuild)
echo "🔄 Restarting app container..."
sshpass -p 'amir13579' ssh root@66.94.110.211 "docker compose restart app 2>&1 | tail -5"

echo "✅ Deployment complete!"
echo "🌐 Visit: https://66.94.110.211/arena/login"
