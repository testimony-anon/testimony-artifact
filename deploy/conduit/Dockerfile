# Subject application: Conduit (TonyMckes/conduit-realworld-example-app)
# Pinned commit: the source tarball is fetched by hash; the deployment does not follow upstream.
FROM node:22-alpine

ARG CONDUIT_COMMIT=5e127d8569b300e0a21dc2c20ea680da4967b1aa
RUN wget -qO /tmp/src.tar.gz "https://github.com/TonyMckes/conduit-realworld-example-app/archive/${CONDUIT_COMMIT}.tar.gz" \
    && mkdir /app \
    && tar -xzf /tmp/src.tar.gz -C /app --strip-components=1 \
    && rm /tmp/src.tar.gz

WORKDIR /app
RUN npm install

# The frontend's static build is served by the backend under NODE_ENV=production (HashRouter, no history fallback needed).
RUN npm run build -w frontend

ENV NODE_ENV=production
WORKDIR /app/backend
EXPOSE 3001
CMD ["node", "index.js"]
