FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive MPLCONFIGDIR=/tmp/matplotlib PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENTRYPOINT ["python", "main.py"]
CMD ["compare", "-s", "iperf3-servers.csv", "-c", "10", "-t", "60", "-g", "1", "-r", "3", "-o", "/results"]
