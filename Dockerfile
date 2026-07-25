# Dockerfile for free cloud hosting (Render, Koyeb, Hugging Face)
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Copy requirement files
COPY requirements.txt .

# Install dependencies matching Playwright 1.40.0
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

# Copy application files
COPY . .

# Expose port
EXPOSE 5000

# Start Mobile Web App server
CMD ["python", "web_app.py"]
