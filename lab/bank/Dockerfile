FROM php:8.1-apache

RUN docker-php-ext-install mysqli

# Route Apache access log to shared volume path so Wazuh can monitor it
RUN mkdir -p /var/log/bank && \
    sed -i 's|CustomLog ${APACHE_LOG_DIR}/access.log combined|CustomLog /var/log/bank/access.log combined|' \
    /etc/apache2/sites-enabled/000-default.conf

COPY . /var/www/html/
RUN chown -R www-data:www-data /var/www/html && \
    find /var/www/html -type f -name "*.php" -exec chmod 644 {} \;

EXPOSE 80
