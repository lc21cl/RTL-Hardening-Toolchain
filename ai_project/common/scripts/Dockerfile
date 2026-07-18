FROM python:3.10-slim

# 安装系统依赖: yosys, iverilog, GTKWave
RUN apt-get update && apt-get install -y --no-install-recommends \
    yosys \
    iverilog \
    gtkwave \
    python3-tk \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    flask \
    pyverilog \
    numpy

# 复制代码
COPY . .

# 默认启动Web GUI
EXPOSE 5000
CMD ["python", "sim/web_gui.py"]
