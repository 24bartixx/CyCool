# Development image: runs the Vite dev server with hot reload.
FROM node:24-alpine

WORKDIR /app

COPY package.json package-lock.json ./
# `npm install` (not `npm ci`) tolerates lockfiles generated on another OS/npm version.
RUN npm install

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
