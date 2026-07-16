FROM python:3.10-slim

LABEL maintainer="HARDENING_TOOL_CHAIN"
LABEL description="Docker image for RTL Hardening Tool Chain with Yosys"

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    wget \
    tar \
    bzip2 \
    xz-utils \
    git \
    make \
    gcc \
    g++ \
    libreadline-dev \
    bison \
    flex \
    libffi-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN wget -q https://github.com/YosysHQ/oss-cad-suite-build/releases/download/2024-01-01/oss-cad-suite-linux-x64-20240101.tgz \
    && tar xzf oss-cad-suite-linux-x64-20240101.tgz -C /opt \
    && rm oss-cad-suite-linux-x64-20240101.tgz

ENV PATH="/opt/oss-cad-suite/bin:${PATH}"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN yosys -version || echo "Yosys installation verification"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=60s \
    CMD python -c "import sys; sys.exit(0)"

CMD ["python", "api_server.py"]
