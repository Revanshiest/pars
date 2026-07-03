FROM nginx:1.27-alpine

RUN apk add --no-cache wget

COPY http-only.conf /etc/nginx/http-only.conf
COPY https-selfsigned.conf /etc/nginx/https-selfsigned.conf
COPY https.conf.template /etc/nginx/https.conf.template
COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 80 443

HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD wget -qO- http://127.0.0.1/nginx-health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
