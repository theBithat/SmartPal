#!/bin/bash

# Production CSS build script for SmartPal Arena
echo "🎨 Building production CSS..."

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
fi

# Build minified CSS
npm run build:css

echo "✅ CSS build complete!"
echo "📦 Output: static/css/output.css"
