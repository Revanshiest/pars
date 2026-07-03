FROM nginx:1.27-alpine

RUN apk add --no-cache wget

COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80 443 8080

HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD wget -qO- http://127.0.0.1:8080/nginx-health || exit 1
