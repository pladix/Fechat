FROM python:3.11-slim

WORKDIR /app

# Instala dependências do sistema necessárias para criptografia
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala dependências do Python
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copia código da aplicação
COPY . /app

# Cria diretórios de uploads
RUN mkdir -p uploads/avatars uploads/media uploads/vault

EXPOSE 8000

ENV PORT=8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
