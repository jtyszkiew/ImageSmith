# Use official Python image as base
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

RUN mv configuration.example.yml configuration.yml
RUN mkdir -p /app/custom_workflows

# Create volumes
VOLUME ["/app/custom_workflows", "/app/plugins"]

# Command to run the application
CMD ["python", "main.py"]
