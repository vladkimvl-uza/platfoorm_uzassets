FROM nginx:1.27-alpine

# Strip default site
RUN rm -f /etc/nginx/conf.d/default.conf

COPY nginx.conf       /etc/nginx/nginx.conf
COPY conf.d/          /etc/nginx/conf.d/

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -q -O - http://127.0.0.1/__nginx_health__ || exit 1

EXPOSE 80 443
