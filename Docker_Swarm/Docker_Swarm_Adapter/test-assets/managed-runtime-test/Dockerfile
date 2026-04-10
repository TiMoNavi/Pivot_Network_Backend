FROM python:3.11-alpine

LABEL io.pivot.runtime.base_image="pivotcompute/runtime-base:alpine-3.20"
LABEL io.pivot.runtime.contract_version="v1"
LABEL io.pivot.runtime.buyer_agent="v1"

RUN mkdir -p /opt/pivot

COPY shell-agent.py /opt/pivot/shell-agent.py

RUN printf '%s\n' \
  '#!/bin/sh' \
  'exec python3 /opt/pivot/shell-agent.py' \
  > /usr/local/bin/pivot-shell-agent \
  && chmod +x /usr/local/bin/pivot-shell-agent

HEALTHCHECK --interval=10s --timeout=3s --retries=3 CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7681/health', timeout=2)"

EXPOSE 7681

CMD ["/usr/local/bin/pivot-shell-agent"]
