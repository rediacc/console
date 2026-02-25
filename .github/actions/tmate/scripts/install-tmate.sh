#!/bin/bash
set -e

echo "📦 Installing tmate..."

# Detect OS
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
    Linux*)
        echo "Detected: Linux ($ARCH)"

        # Try package manager first (faster)
        if command -v apt-get &> /dev/null; then
            echo "Using apt-get..."
            sudo apt-get update -qq
            sudo apt-get install -y -qq tmate
        elif command -v yum &> /dev/null; then
            echo "Using yum..."
            sudo yum install -y tmate
        elif command -v pacman &> /dev/null; then
            echo "Using pacman..."
            sudo pacman -Sy --noconfirm tmate
        else
            # Fallback to binary installation
            echo "No package manager found, downloading binary..."
            case "$ARCH" in
                x86_64)
                    TMATE_URL="https://github.com/tmate-io/tmate/releases/download/2.4.0/tmate-2.4.0-static-linux-amd64.tar.xz"
                    ;;
                aarch64|arm64)
                    TMATE_URL="https://github.com/tmate-io/tmate/releases/download/2.4.0/tmate-2.4.0-static-linux-arm64v8.tar.xz"
                    ;;
                *)
                    echo "❌ Unsupported architecture: $ARCH"
                    exit 1
                    ;;
            esac

            curl -L "$TMATE_URL" -o /tmp/tmate.tar.xz
            tar -xf /tmp/tmate.tar.xz -C /tmp
            sudo mv /tmp/tmate-*/tmate /usr/local/bin/
            sudo chmod +x /usr/local/bin/tmate
            rm -rf /tmp/tmate*
        fi
        ;;

    Darwin*)
        echo "Detected: macOS"
        if command -v brew &> /dev/null; then
            echo "Using Homebrew..."
            brew install tmate
        else
            echo "❌ Homebrew not found. Please install Homebrew first."
            exit 1
        fi
        ;;

    MINGW*|MSYS*|CYGWIN*)
        echo "Detected: Windows"
        echo "Downloading tmate for Windows..."
        curl -L "https://github.com/tmate-io/tmate/releases/download/2.4.0/tmate-2.4.0-static-windows-amd64.zip" -o /tmp/tmate.zip
        unzip -q /tmp/tmate.zip -d /tmp
        mkdir -p /usr/local/bin
        mv /tmp/tmate-*/tmate.exe /usr/local/bin/
        chmod +x /usr/local/bin/tmate.exe
        rm -rf /tmp/tmate*
        ;;

    *)
        echo "❌ Unsupported OS: $OS"
        exit 1
        ;;
esac

# Verify installation
if command -v tmate &> /dev/null; then
    tmate -V
    echo "✅ tmate installed successfully"
else
    echo "❌ tmate installation failed"
    exit 1
fi
