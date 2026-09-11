FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SHORTENER_DATABASE=/data/shortener.db
WORKDIR /service
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock \
    && groupadd --gid 10001 shortener \
    && useradd --uid 10001 --gid 10001 --no-create-home shortener \
    && mkdir /data && chown shortener:shortener /data
COPY app ./app
COPY server.py entrypoint.sh ./
RUN chmod +x entrypoint.sh
EXPOSE 8000
# The entrypoint drops to uid 10001 after preparing the mounted volume.
ENTRYPOINT ["/service/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
