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
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY .streamlit/ ./.streamlit/
COPY VERSION .

EXPOSE 8501
ENV PYTHONPATH=/app/src
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
CMD ["streamlit", "run", "src/app.py"]
