# Build context: repository root.
FROM node:22-alpine AS build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM nginx:stable-alpine
RUN apk add --no-cache openssl
COPY deploy/nginx.conf /etc/nginx/nginx.conf.template
COPY deploy/web-entrypoint.sh /web-entrypoint.sh
COPY --from=build /web/dist /usr/share/nginx/html
RUN chmod +x /web-entrypoint.sh
EXPOSE 80 443
ENTRYPOINT ["/web-entrypoint.sh"]
