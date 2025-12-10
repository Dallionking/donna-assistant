#!/bin/bash

# Donna Personal Assistant - Setup Script

echo "🤖 Setting up Donna Personal Assistant..."
echo ""

# Navigate to backend directory
cd "$(dirname "$0")/backend" || exit 1

# Check Python version
python_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
required_version="3.11"

echo "📦 Checking Python version..."
if [[ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]]; then
    echo "❌ Python $required_version+ required. Found: $python_version"
    exit 1
fi
echo "✅ Python $python_version"

# Create virtual environment
echo ""
echo "📦 Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo ""
    echo "📝 Creating .env file from template..."
    cp env-example.txt .env
    echo "⚠️  Please edit backend/.env with your API keys!"
fi

# Create credentials directory
mkdir -p credentials

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit backend/.env with your API keys"
echo "2. Set up Google OAuth credentials (see README.md)"
echo "3. Create Telegram bot via @BotFather"
echo "4. Run Donna: cd backend && source venv/bin/activate && python -m donna.main"
echo ""
echo "Or just use Donna directly in Cursor! Open the workspace and start chatting."


