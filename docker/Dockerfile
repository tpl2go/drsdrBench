FROM python:3.14@sha256:8428c32065df71d5a7763099ccb8ee215314129b50d395f95ad589151887d52f
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g opencode-ai@1.4.3
WORKDIR /runner
COPY runner.py /runner/runner.py
ENTRYPOINT ["python3", "/runner/runner.py"]
