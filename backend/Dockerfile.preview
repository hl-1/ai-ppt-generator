# Optional worker/API image with real PPTX rendering. Keep the normal image lightweight.
ARG BASE_IMAGE=aippt-backend
FROM ${BASE_IMAGE}
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-impress poppler-utils fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
ENV PREVIEW_SOFFICE=/usr/bin/soffice PREVIEW_PDFTOPPM=/usr/bin/pdftoppm
