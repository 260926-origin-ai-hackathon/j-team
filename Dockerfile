# ヘヤカルテを配信するだけの静的サーバー。周辺データ（data/area.json）はビルド済みのものを同梱する
FROM nginx:1.27-alpine

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
COPY data/ /usr/share/nginx/html/data/

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/data/area.json >/dev/null || exit 1
