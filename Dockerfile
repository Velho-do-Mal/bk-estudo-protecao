# Dockerfile — BK Estudo de Proteção v2
# Python 3.12-slim (alinhado com runtime.txt e .python-version)
FROM python:3.12-slim

# Instala dependências de sistema para WeasyPrint (Cairo, Pango, GDK-Pixbuf)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    libcairo2 \
    libcairo-gobject2 \
    && rm -rf /var/lib/lists/*

WORKDIR /app

# Instala dependências Python
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copia código da aplicação
COPY . .

# Expõe porta padrão do Streamlit (Render injeta $PORT em runtime)
EXPOSE 8501

# Comando de inicialização — Streamlit (interface principal do usuário)
CMD streamlit run streamlit_app.py \
    --server.port ${PORT:-8501} \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false
