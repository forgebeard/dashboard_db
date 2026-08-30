FROM python:3.11-slim

WORKDIR /app

# Официальные репозитории Debian плюс зеркала: Fastly (deb.debian.org) бывает недоступен.
RUN set -eux; \
    printf '%s\n' \
      'Acquire::http::Timeout "8";' \
      'Acquire::https::Timeout "8";' \
      'Acquire::Retries "2";' \
      > /etc/apt/apt.conf.d/99timeouts; \
    for src in /etc/apt/sources.list.d/debian.sources /etc/apt/sources.list; do \
      [ -f "$src" ] || continue; \
      sed -i \
        -e 's|URIs: http://deb.debian.org/debian-security[[:space:]]*|URIs: http://deb.debian.org/debian-security http://mirror.yandex.ru/debian-security |' \
        -e 's|URIs: http://deb.debian.org/debian[[:space:]]*$|URIs: http://deb.debian.org/debian http://ftp.ru.debian.org/debian http://mirror.yandex.ru/debian|' \
        "$src"; \
    done; \
    if ! apt-get update; then \
      for src in /etc/apt/sources.list.d/debian.sources /etc/apt/sources.list; do \
        [ -f "$src" ] || continue; \
        sed -i \
          -e 's|http://deb.debian.org/debian-security|http://mirror.yandex.ru/debian-security|g' \
          -e 's|http://deb.debian.org/debian|http://mirror.yandex.ru/debian|g' \
          "$src"; \
      done; \
      apt-get update; \
    fi; \
    apt-get install -y --no-install-recommends curl; \
    rm -rf /var/lib/apt/lists/*; \
    groupadd --gid 1000 appuser; \
    useradd --uid 1000 --gid appuser --create-home --shell /usr/sbin/nologin appuser; \
    mkdir -p /app/logs; \
    chown -R appuser:appuser /app

COPY --chown=appuser:appuser requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser .streamlit/ ./.streamlit/
COPY --chown=appuser:appuser VERSION .

USER appuser

EXPOSE 8501
ENV PYTHONPATH=/app/src
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
CMD ["streamlit", "run", "src/app.py"]
