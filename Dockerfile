FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 QINGHE_DB=/srv/state/qinghe.sqlite3
WORKDIR /srv/qinghe
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home flood && mkdir -p /srv/state && chown flood:flood /srv/state
COPY app/ app/
COPY data/ data/
USER flood
EXPOSE 8000
CMD ["python","-m","uvicorn","app.api:app","--host","0.0.0.0","--port","8000","--workers","1"]
