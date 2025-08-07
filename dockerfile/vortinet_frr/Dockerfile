FROM vortinet_base

# 设置环境变量，以确保安装过程中无交互
ENV DEBIAN_FRONTEND=noninteractive

# 添加 FRR 的 GPG 密钥
RUN curl -fsSL https://deb.frrouting.org/frr/keys.gpg | tee /usr/share/keyrings/frrouting.gpg > /dev/null

# 添加 FRR 的 APT 软件源
RUN echo deb '[signed-by=/usr/share/keyrings/frrouting.gpg]' https://deb.frrouting.org/frr \
     $(lsb_release -s -c) frr-stable | tee -a /etc/apt/sources.list.d/frr.list
# 更新 APT 包索引并安装 FRR 和相关工具
RUN apt-get update && apt-get install -y frr frr-pythontools frr-rpki-rtrlib

# 清理不必要的文件，减小镜像大小
RUN apt clean && \
    rm -rf /tmp/* /var/lib/apt/lists/* /var/tmp/*
