FROM php:8.4-cli-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libsqlite3-dev \
    && docker-php-ext-install pdo_sqlite && rm -rf /var/lib/apt/lists/*
COPY style.html /opt/style.html
COPY router.php /opt/router.php
COPY php.ini /usr/local/etc/php/conf.d/lab.ini
USER 1000:1000
WORKDIR /work
CMD ["php", "-S", "0.0.0.0:8080", "-t", "/work"]
