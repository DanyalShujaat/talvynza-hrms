FROM node:22-alpine AS build
WORKDIR /repo
COPY packages/shared-types ./packages/shared-types
COPY apps/web/package*.json ./apps/web/
RUN cd apps/web && npm ci
COPY apps/web ./apps/web
RUN cd apps/web && npm run build

FROM nginx:1.27-alpine
COPY infrastructure/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html
EXPOSE 80
