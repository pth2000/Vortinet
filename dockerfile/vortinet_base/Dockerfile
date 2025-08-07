FROM ubuntu:20.04

# 禁用交互模式
ENV DEBIAN_FRONTEND=noninteractive

# 更新包列表并安装必要的软件
RUN apt-get update && \
    apt-get install -y \
    build-essential \
    git \
    curl \
    lsb-release \
    libconfuse-dev \
    gengetopt \
    libcap2-bin \
    libzmq3-dev \
    libxml2-dev \
    iputils-ping \
    net-tools \
    iproute2 \
    iperf3 \
    traceroute \
    python3 \
    python3-pip \
    vim && \
    apt-get autoclean && \
    apt-get autoremove

