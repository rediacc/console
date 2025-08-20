# Use Playwright's official image with browsers pre-installed
FROM mcr.microsoft.com/playwright:v1.52.0-jammy

# Install Python and required system packages
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /console/playwright

# Copy Python requirements and install dependencies
COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# Install playwright browsers (they should already be there, but ensure they're available)
RUN python3 -m playwright install --with-deps

# Copy test files and configuration
COPY . .

# Set environment variables for Playwright
ENV PYTHONPATH=/console/playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Default command - run the main test suite
CMD ["python3", "smart/00_all.py"]