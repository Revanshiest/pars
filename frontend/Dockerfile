# SPA static files (internal; public access via deploy/nginx)
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package.json ./
RUN npm install
COPY frontend/ .
ARG VITE_API_URL=
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.27-alpine
RUN apk add --no-cache wget
COPY frontend/nginx-spa.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK CMD wget -qO- http://localhost/ || exit 1
