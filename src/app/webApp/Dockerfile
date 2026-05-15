FROM python:3.11-slim

WORKDIR /app

# Install Azure CLI so DefaultAzureCredential -> AzureCliCredential can reuse the
# host's `az login` cache (mounted at /root/.azure by docker-compose).
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && curl -sL https://aka.ms/InstallAzureCLIDeb | bash \
 && rm -rf /var/lib/apt/lists/*

# Install deps first for better layer caching
COPY src/app/webApp/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the canonical agenda.md (build context = project root) and the app code
COPY agenda.md ./agenda.md
COPY content ./content
COPY data/contoso ./data/contoso
COPY data/industries ./data/industries
COPY src/app/webApp/app ./

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
