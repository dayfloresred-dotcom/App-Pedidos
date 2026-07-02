FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

# La app cachea el catalogo de productos en memoria del proceso:
# mantener SIEMPRE --workers 1 (mas workers = caches inconsistentes).
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080", "--timeout", "120", "--workers", "1"]
