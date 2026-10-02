# Web image: Next.js static export served by nginx on :8080 (Cloud Run's port).
# The API URL is baked into the bundle at build time.

FROM node:24-slim AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/out /usr/share/nginx/html
EXPOSE 8080
