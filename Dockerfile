FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir flask gunicorn werkzeug pyotp qrcode[pil]

COPY app.py .
COPY templates/ ./templates/

RUN mkdir -p /app/storage /app/meta

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "app:app"]
