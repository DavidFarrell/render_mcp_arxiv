FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the server script
COPY arxiv_mcp_http_server.py .

# Create papers directory for storing arxiv data
RUN mkdir -p papers

# The server reads PORT from environment variable
CMD ["python", "arxiv_mcp_http_server.py"]