# ==============================================================================
# chacha-bot 프론트엔드 + nginx Dockerfile
#
# 명세서 I1: React는 multi-stage 빌드로 nginx 이미지 안에 정적 파일로 넣어요.
# nginx 설정(nginx/default.conf)은 이미지에 넣지 않고 docker-compose.yaml에서 마운트해요.
# ==============================================================================

# ------------------------------------------------------------------------------
# 1단계: React 빌드 (Vite 8은 Node 20.19 이상 또는 22.12 이상이 필요해요)
# ------------------------------------------------------------------------------
FROM node:22-alpine AS build

WORKDIR /app

# Docker 레이어 캐싱을 위해 의존성 목록 파일을 먼저 복사하여 설치
# package-lock.json에 적힌 버전 그대로 설치하려고 npm install 대신 npm ci를 써요
COPY package.json package-lock.json ./
RUN npm ci

# 소스 코드 복사 후 빌드 (결과물: /app/dist)
COPY . .
RUN npm run build

# ------------------------------------------------------------------------------
# 2단계: 빌드 결과물만 nginx 이미지에 담기 (node와 node_modules는 최종 이미지에 남지 않아요)
# ------------------------------------------------------------------------------
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
