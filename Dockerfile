# Dockerfile for free cloud hosting (Render, Koyeb, Hugging Face)
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Point Playwright to standard pre-installed browser directory and force unbuffered logging
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=UTF-8

WORKDIR /app

# Copy requirement files
COPY requirements.txt .

# Install dependencies matching Playwright 1.40.0
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium --with-deps
RUN chmod -R 777 /ms-playwright

# Copy application files
COPY . .

# Expose port
EXPOSE 5000

# Start Mobile Web App server
CMD ["python", "web_app.py"]
