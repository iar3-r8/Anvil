FROM nvidia/cuda:12.5.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install Python and dependencies
RUN apt-get update && apt-get install -y \
    python3-pip python3-dev git curl \
    && rm -rf /var/lib/apt/lists/*

# Install vLLM
RUN pip3 install --upgrade pip
RUN pip3 install "fastapi<0.137" vllm==0.17.1

# Set entrypoint to match the official vLLM server
ENTRYPOINT ["python3", "-m", "vllm.entrypoints.openai.api_server"]