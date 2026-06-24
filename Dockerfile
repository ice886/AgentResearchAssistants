FROM python:3.12-slim

# 非 root 用户（uid=1000），与 SandboxManager config 匹配
RUN useradd -m -u 1000 researcher

# 常用 ML 依赖（轻量基础镜像；实验代码可在运行时 pip install）
RUN pip install --no-cache-dir \
    numpy \
    pandas \
    scikit-learn \
    matplotlib \
    torch \
    torchvision \
    --extra-index-url https://download.pytorch.org/whl/cpu

WORKDIR /workspace
USER researcher

CMD ["python3"]
