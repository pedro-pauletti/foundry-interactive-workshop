FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && curl -sL https://aka.ms/InstallAzureCLIDeb | bash \
 && rm -rf /var/lib/apt/lists/*

COPY src/app/mafwAgent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/app/mafwAgent/app ./

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8091"]
