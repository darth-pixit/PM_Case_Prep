# Generic container — works on Railway, Fly.io, Cloud Run, a VPS, anywhere.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8000
CMD ["sh", "-c", "uvicorn pmcaseprep.web.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
