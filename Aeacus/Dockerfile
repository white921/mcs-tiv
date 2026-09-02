FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY aeacus_lab ./aeacus_lab
COPY tests ./tests

ENTRYPOINT ["python", "-m", "aeacus_lab.experiment"]
CMD ["--scenario", "all", "--results-dir", "/app/results"]
