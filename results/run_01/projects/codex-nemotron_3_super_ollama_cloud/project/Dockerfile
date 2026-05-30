# Use Python 3.13.13 slim image
FROM python:3.13.13-slim

# Install Node.js and npm for Tailwind CSS
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        gnupg \
        && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
        && apt-get install -y --no-install-recommends nodejs \
        && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Build Tailwind CSS
RUN npm run buildcss

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose port 8000
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the application using Daphne (ASGI server)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
