FROM python:3.11-slim

# Instala dependências de sistema para WeasyPrint (Cairo, Pango, GDK-Pixbuf)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    libcairo2 \
    libcairo-gobject2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala dependências Python
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copia código da aplicação
COPY . .

# Expõe porta (Render injeta $PORT em runtime)
EXPOSE 8000

# Comando de inicialização
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
