# syntax=docker/dockerfile:1
FROM --platform=linux/amd64 python:3.10-slim

# Set working directory
WORKDIR /app

# Copy source code
COPY main.py pdf_processor.py requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create I/O directories 
RUN mkdir -p app\input app\output

# Set entrypoint
CMD ["python", "main.py"]
