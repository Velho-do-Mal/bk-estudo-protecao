# Dockerfile — BK Estudo de Proteção v2
# Python 3.12-slim (alinhado com runtime.txt e .python-version)
FROM python:3.12-slim

# Nota: dependências de sistema para WeasyPrint (Cairo, Pango, GDK-Pixbuf) foram
# removidas — a geração de relatórios usa python-docx (app/reports/service.py),
# WeasyPrint não é mais importado em lugar nenhum do código.

WORKDIR /app

# Instala dependências Python
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copia código da aplicação
COPY . .

# Expõe porta padrão da aplicação (Railway injeta $PORT em runtime)
EXPOSE 8000

# Comando de inicialização — FastAPI/Jinja2 (interface principal do usuário)
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
