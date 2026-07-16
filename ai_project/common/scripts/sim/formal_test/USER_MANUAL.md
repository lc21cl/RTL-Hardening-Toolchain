# RTL 加固工具链用户手册

> 版本：1.0.0 ｜ 适用目录：`ai_project/common/scripts/sim/formal_test/`

本手册详细介绍 RTL 加固工具链的安装、使用、API 调用与部署方式。工具链基于 GraphSAGE 图神经网络进行电路脆弱性预测，并结合 RAG-LLM 自动生成加固后的 RTL 代码。

---

## 目录

1. [简介](#1-简介)
2. [安装指南](#2-安装指南)
3. [快速开始](#3-快速开始)
4. [命令行工具](#4-命令行工具)
5. [REST API 文档](#5-rest-api-文档)
6. [加固策略说明](#6-加固策略说明)
7. [Docker 部署](#7-docker-部署)
8. [配置文件](#8-配置文件)
9. [测试](#9-测试)
10. [FAQ](#10-faq)

---

## 1. 简介

### 1.1 工具链概述

RTL 加固工具链是一套面向数字电路设计的可靠性加固自动化工具，融合了图神经网络（GNN）脆弱性预测、检索增强生成（RAG）与大语言模型（LLM）加固代码生成、AST 级自动修复、Yosys 综合验证等技术，覆盖从设计分析到加固部署的完整流程。

工具链的核心思路：
1. 将 RTL/BLIF/AIG 电路转换为图结构（PyG Data）；
2. 使用训练好的 GraphSAGE 模型推理每个节点的脆弱性概率；
3. 基于脆弱性结果检索加固模式知识库，并由 LLM 生成加固 RTL；
4. 通过 AST 修复与 Yosys 综合验证迭代，确保加固后代码语法与功能正确。

### 1.2 核心功能列表

| 功能模块 | 描述 |
|---------|------|
| GNN 脆弱性推理 | 基于 GraphSAGE 模型对电路节点进行脆弱性打分 |
| RAG-LLM 加固 | 检索加固模式知识库，结合 LLM 生成加固 RTL |
| 自动修复 | AST 级缺陷检测、语法修复与 Yosys 验证迭代 |
| 综合管线 | RTL → AIG/BLIF → PyG → 推理 → 加固的一体化流程 |
| REST API 服务 | FastAPI 接口，支持远程调用与 CI/CD 集成 |
| Web GUI | 浏览器端的模块级策略配置界面 |
| 大规模推理 | 面向 10 万+ 节点的分块、半精度、渐进式推理 |
| 模型压缩 | 量化（int8/float16）、剪枝、TorchScript 优化 |
| FPGA 部署 | HLS 综合、ONNX 导出、资源占用分析 |
| 13 种加固策略 | TMR、ECC、DICE、Parity、BCH、CRC 等策略库 |

---

## 2. 安装指南

### 2.1 环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows 10+ / Linux / macOS |
| Python | 3.10 及以上 |
| Yosys | 0.9+ （用于综合与形式验证，可选但推荐） |
| Docker | 20.10+ （可选，用于容器化部署） |
| GPU | 可选，CUDA 11.7+ 用于 GPU 训练与推理 |

### 2.2 Python 依赖安装

进入工具目录后安装依赖：

```bash
cd ai_project/common/scripts/sim/formal_test

# 安装核心依赖
pip install torch torch-geometric numpy pyyaml

# 安装 API 服务依赖
pip install fastapi uvicorn pydantic

# 安装可选依赖（按需）
pip install openai          # RAG-LLM 加固（OpenAI 后端）
pip install networkx       # 图分析
pip install tqdm            # 进度条（大规模推理）
pip install pytest          # 测试
```

若存在 `requirements.txt`，可直接：

```bash
pip install -r requirements.txt
```

### 2.3 Yosys 安装

Yosys 用于 RTL 综合与形式验证，工具链支持三种方式使用 Yosys。

#### 方式一：自动安装（推荐）

工具链在运行时会通过 `yosys_utils.find_yosys()` 自动检测以下路径：

1. 系统 PATH 中的 `yosys` / `yosys.exe`
2. 项目根目录下的 `tools/oss-cad-suite/oss-cad-suite/bin`
3. Docker 镜像（见 2.4）

下载 [oss-cad-suite](https://github.com/YosysHQ/oss-cad-suite-build/releases) 并解压到项目根目录的 `tools/oss-cad-suite/` 下，工具链会自动识别。

#### 方式二：手动安装

**Windows：**
1. 从 [YosysHQ 下载页](https://github.com/YosysHQ/yosys/releases) 下载 Windows 预编译包；
2. 解压后将 `bin` 目录加入系统 PATH。

**Linux：**
```bash
# Ubuntu / Debian
sudo apt-get install yosys

# 或从源码编译
git clone https://github.com/YosysHQ/yosys.git
cd yosys
make -j$(nproc)
sudo make install
```

**macOS：**
```bash
brew install yosys
```

验证安装：
```bash
yosys -version
```

#### 方式三：Docker 容器

若本地未安装 Yosys，工具链会自动通过 `yosys_docker.py` 调用官方 Docker 镜像 `ghcr.io/yosyshq/yosys:latest` 执行综合与验证。详见 [7. Docker 部署](#7-docker-部署)。

### 2.4 Docker 方式

使用仓库自带的 `Dockerfile` 构建完整环境（包含 Yosys）：

```bash
# 构建镜像
docker build -t rtl-hardening-toolchain .

# 运行 API 服务
docker run -p 8000:8000 rtl-hardening-toolchain

# 交互式运行
docker run -it --rm -v $(pwd):/app rtl-hardening-toolchain bash
```

镜像基于 `python:3.10-slim`，内置 oss-cad-suite 与全部 Python 依赖。

---

## 3. 快速开始

### 3.1 五分钟上手指南

以下示例演示完整流程：加载模型 → 推理 BLIF 设计 → 输出脆弱节点报告。

**前置准备：**
- 已安装 Python 3.10+ 与依赖
- 已有训练好的模型 `data/models/local_best_model.pt`
- 已有 BLIF 设计文件（如 `data/blifs/design.blif`）

**执行命令：**

```bash
# 进入工具目录
cd ai_project/common/scripts/sim/formal_test

# 运行 GNN 脆弱性推理
python gnn_inference.py --blif data/blifs/design.blif --output result.json
```

**预期输出：**

```
==============================================================
  Vulnerability Inference Report
==============================================================
  File:     design.blif
  Type:     blif
  Nodes:    1024
  Edges:    2048
  Features: 12-dim
--------------------------------------------------------------
  Score Distribution:
    Max:   0.8421
    Mean:  0.0532
    Min:   0.0001
    Std:   0.1023
--------------------------------------------------------------
  Threshold:         0.05
  Vulnerable nodes:  87 / 1024 (8.5%)
--------------------------------------------------------------
  Top-5 Most Vulnerable Nodes:
      1. Node    42  Score: 0.842100
      2. Node   128  Score: 0.765400
      3. Node   256  Score: 0.654300
      4. Node    17  Score: 0.543200
      5. Node   512  Score: 0.432100
==============================================================

  Inference time: 45.2 ms
  [Save] Results → result.json
```

**完整加固流程（一键命令）：**

```bash
python graph_pipeline.py --harden target_design.v --hardening-strategy tmr --max-repair-iter 5
```

该命令会自动完成：RTL → 图构建 → 脆弱性分析 → RAG-LLM 加固生成 → AST 修复 → Yosys 验证。

---

## 4. 命令行工具

### 4.1 gnn_inference.py — GNN 脆弱性推理

基于训练好的 GraphSAGE 模型对电路设计进行脆弱性预测。

**基本用法：**

```bash
# 单文件推理（自动识别 BLIF/AIG）
python gnn_inference.py --input design.blif

# 指定 BLIF 文件
python gnn_inference.py --blif design.blif

# 指定 AIG 文件
python gnn_inference.py --aig design.aig

# 批量推理
python gnn_inference.py --batch data/blifs/ --output batch_results.json

# 运行端到端 Demo
python gnn_inference.py --demo

# 带性能基准测试
python gnn_inference.py --blif design.blif --benchmark
```

**参数说明：**

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `--blif` | 字符串 | BLIF 文件路径 | - |
| `--aig` | 字符串 | AIG 文件路径 | - |
| `--input` | 字符串 | 自动识别的输入文件 | - |
| `--batch` | 字符串 | 批量推理目录 | - |
| `--demo` | 开关 | 运行端到端 Demo | false |
| `--model` | 字符串 | 模型 .pt 文件路径 | 自动检测 |
| `--model-type` | 枚举 | 模型架构（SAGE3/SAGE2Lite/auto） | auto |
| `--threshold` | 浮点 | 脆弱性分类阈值 | 0.05 |
| `--output` | 字符串 | 结果输出 JSON 路径 | 自动生成 |
| `--benchmark` | 开关 | 运行延迟基准测试 | false |

### 4.2 rag_integration.py — RAG-LLM 加固

检索加固模式知识库，结合 LLM 生成加固后的 RTL 代码。

**主要作为 Python API 使用：**

```python
from rag_integration import RAGEngine

engine = RAGEngine(llm_backend='mock')  # 或 'openai'
engine.load_knowledge_base()

design_info = {
    'module_name': 'tmr_voter',
    'signals': ['data_in', 'data_out', 'clk', 'rst_n'],
    'signal_width': 32,
}
vulnerability_result = {
    'all_vulnerable_nodes': [{'node_id': 0, 'score': 0.85}],
    'num_nodes': 5,
}
rtl = engine.generate_hardened_rtl(design_info, vulnerability_result)
```

**支持的 LLM 后端：**
- `mock`：内置 Mock LLM，无需 API Key，用于离线测试
- `openai`：OpenAI GPT 系列（需配置 `OPENAI_API_KEY`）
- `deepseek`：DeepSeek 模型

**直接运行：**
```bash
python rag_integration.py
```
执行内置的层次化提取测试。

### 4.3 auto_repair.py — 自动修复

基于 AST 与正则模式的 Verilog 代码自动修复模块。

**核心能力：**
- Verilog AST 解析与缺陷检测
- 单触发器检测与 TMR 修复生成
- 缺失复位检测与复位修复
- 语法错误修复（缺失 `end`、`endgenerate`、分号、case default 等）
- Yosys 综合验证迭代

**Python API：**

```python
from auto_repair import auto_repair, generate_repair_report

repaired_code, actions = auto_repair(verilog_code)
print(generate_repair_report(actions))
```

该模块主要由 `graph_pipeline.py` 与 `api_server.py` 内部调用，不单独提供命令行入口。

### 4.4 graph_pipeline.py — 综合管线

统一 AIG/BLIF 图构建管线，集成 RAG 加固与自动修复。

**基本用法：**

```bash
# 从 BLIF 构建图
python graph_pipeline.py --blif design.blif --stats

# 从 AIG 构建图
python graph_pipeline.py --aig design.aig --visualize --output graph.png

# 从 RTL 综合（需要 Yosys）
python graph_pipeline.py --rtl design.v --output data.pt

# 批量转换
python graph_pipeline.py --batch blifs/ --output training_data.pt

# RAG 加固管线
python graph_pipeline.py --harden target.v \
    --hardening-strategy tmr \
    --llm-backend mock \
    --max-repair-iter 5

# 列出设计中的模块
python graph_pipeline.py --rtl design.v --list-modules

# 静态设计错误分析
python graph_pipeline.py --rtl design.v --analyze-design-errors
```

**参数说明：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `--blif` | 字符串 | 单个 BLIF 文件 |
| `--aig` | 字符串 | 单个 AIG 文件 |
| `--rtl` | 字符串 | RTL Verilog 文件 |
| `--batch` | 字符串 | 批量转换目录 |
| `--harden` | 字符串 | 对 RTL 执行 RAG+自动修复加固 |
| `--output` | 字符串 | 输出路径（.pt 或 .png） |
| `--visualize` | 开关 | 可视化图结构 |
| `--stats` | 开关 | 打印统计信息 |
| `--list-modules` | 开关 | 列出模块声明 |
| `--yosys-script` | 字符串 | Yosys 综合脚本 |
| `--llm-backend` | 枚举 | LLM 后端（mock/openai/deepseek） |
| `--max-repair-iter` | 整数 | 自动修复最大迭代次数（默认 5） |
| `--hardening-strategy` | 枚举 | 加固策略（tmr/ecc/dice/parity） |
| `--analyze-design-errors` | 开关 | 静态设计错误分析 |
| `--submodule` | 字符串 | 子模块搜索目录（可多次指定） |
| `--design-files` | 字符串 | 附加 RTL 文件（可多次指定） |
| `--use-ast-repair` | 开关 | 启用 AST 语法修复（默认开） |
| `--no-ast-repair` | 开关 | 禁用 AST 语法修复 |
| `--docker-verify` | 开关 | 用 Docker Yosys 验证 |

### 4.5 api_server.py — REST API 服务

基于 FastAPI 的 RESTful API 服务，支持远程调用与 CI/CD 集成。

**启动服务：**

```bash
# 开发模式（自动重载）
python api_server.py

# 生产模式
uvicorn api_server:app --host 0.0.0.0 --port 8000 --workers 4
```

服务默认监听 `0.0.0.0:8000`，启动后访问：
- API 文档（Swagger）：`http://localhost:8000/docs`
- ReDoc 文档：`http://localhost:8000/redoc`

详见 [5. REST API 文档](#5-rest-api-文档)。

### 4.6 web_gui.py — Web GUI

浏览器端的模块级加固策略配置界面。

**启动方式：**

主要通过 `rag_integration.py` 的 `open_web_gui()` 函数启动：

```python
from rag_integration import open_web_gui

web_gui = open_web_gui(
    design_analysis=analysis_result,
    module_strategy_map=strategy_map,
    hardening_callback=run_hardening,
    port=8080,
)
```

启动后自动打开浏览器访问 `http://localhost:8080`。

**Web GUI 端点：**
- `GET /` — 主页面
- `GET /api/design` — 获取设计分析与当前策略
- `GET /api/strategies/list` — 获取可用策略列表
- `GET /api/optimization_goals` — 获取优化目标列表
- `POST /api/harden` — 触发加固

### 4.7 setup_api.py — API 配置

交互式配置 OpenAI API Key 的工具。

**用法：**

```bash
# 交互式配置
python setup_api.py

# 检查当前配置状态
python setup_api.py --check
```

交互式流程会提示输入：
1. `OPENAI_API_KEY`（必须以 `sk-` 开头）
2. `OPENAI_MODEL`（默认 `gpt-4`）
3. `OPENAI_BASE_URL`（默认 `https://api.openai.com/v1`）

配置写入 `.env` 文件，并可选立即测试连接。详见 [8. 配置文件](#8-配置文件)。

### 4.8 large_scale_inference.py — 大规模设计推理

面向 10 万+ 节点电路的 GNN 推理工具，支持分块、半精度、渐进式推理。

**基本用法：**

```bash
# 分块推理
python large_scale_inference.py --input big_design.blif --chunk-size 10000

# 渐进式推理（前 50000 节点）
python large_scale_inference.py --input big_design.aig --max-nodes 50000

# 内存估算（不执行推理）
python large_scale_inference.py --input big_design.blif --estimate-only

# 半精度推理
python large_scale_inference.py --input big_design.blif --half-precision

# 图优化后推理
python large_scale_inference.py --input big_design.blif --optimize-graph
```

**参数说明：**

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `--input` | 字符串 | 输入文件（.blif/.aig/.pt） | 必填 |
| `--model` | 字符串 | 模型 .pt 路径 | 自动检测 |
| `--model-type` | 枚举 | 模型架构 | auto |
| `--threshold` | 浮点 | 脆弱性阈值 | 0.05 |
| `--chunk-size` | 整数 | 分块大小 | 10000 |
| `--max-nodes` | 整数 | 渐进式推理节点上限 | - |
| `--max-neighbors` | 整数 | 邻居采样数 | 15 |
| `--num-hops` | 整数 | 子图采样跳数 | 自动 |
| `--device` | 枚举 | 设备（auto/cpu/cuda） | auto |
| `--half-precision` | 开关 | 半精度推理 | false |
| `--no-neighbor-sampling` | 开关 | 禁用邻居采样 | false |
| `--optimize-graph` | 开关 | 图优化 | false |
| `--estimate-only` | 开关 | 仅估算内存 | false |
| `--output` | 字符串 | 输出 JSON 路径 | - |

### 4.9 model_compression.py — 模型压缩

GraphSAGE 模型的量化、剪枝与推理优化工具。

**基本用法：**

```bash
# 量化 + 剪枝
python model_compression.py --model model.pt --quantize int8 --prune 0.3

# 性能基准测试
python model_compression.py --model model.pt --benchmark --runs 200

# 压缩前后对比
python model_compression.py --model model.pt --compare --quantize int8

# 保存压缩后模型
python model_compression.py --model model.pt --quantize int8 --save compressed.pt
```

**参数说明：**

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `--model` | 字符串 | 模型文件路径（必填） | - |
| `--quantize` | 枚举 | 量化精度（int8/float16） | - |
| `--prune` | 浮点 | 剪枝比例（0.0~1.0） | 0.0 |
| `--optimize` | 开关 | 推理优化 | false |
| `--benchmark` | 开关 | 性能基准测试 | false |
| `--compare` | 开关 | 压缩前后对比 | false |
| `--save` | 字符串 | 保存压缩模型路径 | - |
| `--runs` | 整数 | 基准测试次数 | 100 |
| `--nodes` | 整数 | 基准测试图节点数 | 100 |
| `--features` | 整数 | 基准测试特征维度 | 12 |
| `--device` | 字符串 | 设备（cpu/cuda） | cpu |

> **注意：** 命令行模式仅支持 TorchScript 模型。对于 state_dict 格式的 checkpoint，请使用 Python API（`ModelCompressor` 类）并传入模型类。

---

## 5. REST API 文档

API 服务基于 FastAPI 实现，默认监听 `0.0.0.0:8000`。所有请求与响应均为 JSON 格式。

### 5.1 GET /api/health — 健康检查

**请求：** 无参数

**响应：**
```json
{
  "status": "healthy",
  "timestamp": "2026-07-16 10:30:00",
  "version": "1.0.0"
}
```

**示例：**
```bash
curl http://localhost:8000/api/health
```

### 5.2 GET /api/strategies — 获取加固策略列表

**请求：** 无参数

**响应：**
```json
{
  "strategies": [
    {
      "name": "tmr",
      "description": "Triple Modular Redundancy",
      "area_overhead": 3.0,
      "reliability": 5
    }
  ]
}
```

**示例：**
```bash
curl http://localhost:8000/api/strategies
```

### 5.3 POST /api/harden — 加固 RTL 代码

**请求体：**
```json
{
  "rtl_code": "module counter (...); ... endmodule",
  "strategy": "tmr",
  "parameters": null
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `rtl_code` | 字符串 | 是 | 待加固的 RTL 代码 |
| `strategy` | 字符串 | 否 | 加固策略（默认 `tmr`） |
| `parameters` | 对象 | 否 | 策略参数 |

**响应：**
```json
{
  "success": true,
  "hardened_rtl": "module hardened_counter (...); ... endmodule",
  "strategy": "tmr",
  "sdc_constraints": "# SDC constraints ...",
  "metadata": {
    "tokens_used": 1024,
    "model": "MockLLM"
  }
}
```

**示例：**
```bash
curl -X POST http://localhost:8000/api/harden \
  -H "Content-Type: application/json" \
  -d '{"rtl_code": "module test(input clk, output q); endmodule", "strategy": "tmr"}'
```

### 5.4 POST /api/vulnerability — 脆弱性分析

**请求体：**
```json
{
  "rtl_code": "module counter (...); ... endmodule"
}
```

**响应：**
```json
{
  "success": true,
  "results": {
    "signal_name": {
      "vulnerability_score": 0.85,
      "category": "high"
    }
  },
  "summary": {
    "high_vulnerability_count": 3,
    "total_analyzed": 10,
    "model": "GraphSAGE"
  }
}
```

**示例：**
```bash
curl -X POST http://localhost:8000/api/vulnerability \
  -H "Content-Type: application/json" \
  -d '{"rtl_code": "module test(input clk, output q); reg r; endmodule"}'
```

### 5.5 POST /api/compare — 策略对比

**请求体：**
```json
{
  "rtl_code": "module counter (...); ... endmodule",
  "strategies": ["tmr", "ecc", "dice"]
}
```

**响应：**
```json
{
  "success": true,
  "comparison": [
    {
      "strategy": "tmr",
      "area_overhead": 3.0,
      "reliability": 5,
      "latency": 1,
      "power_overhead": 3.0
    }
  ],
  "recommendation": "tmr"
}
```

**示例：**
```bash
curl -X POST http://localhost:8000/api/compare \
  -H "Content-Type: application/json" \
  -d '{"rtl_code": "module test(...); endmodule", "strategies": ["tmr","ecc"]}'
```

### 5.6 POST /api/repair — 修复 RTL 代码

**请求体：**
```json
{
  "rtl_code": "module test(input clk); reg r; always @(posedge clk) r <= 1; endmodule"
}
```

**响应：**
```json
{
  "success": true,
  "repaired_rtl": "module test(...); ... endmodule",
  "errors_found": ["missing reset in always block"],
  "fixes_applied": ["added async reset"]
}
```

**示例：**
```bash
curl -X POST http://localhost:8000/api/repair \
  -H "Content-Type: application/json" \
  -d '{"rtl_code": "module test(input clk); endmodule"}'
```

### 5.7 端点汇总

| 方法 | 路径 | 功能 | 标签 |
|------|------|------|------|
| GET | `/api/health` | 健康检查 | Health |
| GET | `/api/strategies` | 获取策略列表 | Strategies |
| POST | `/api/harden` | 加固 RTL | Hardening |
| POST | `/api/vulnerability` | 脆弱性分析 | Vulnerability |
| POST | `/api/compare` | 策略对比 | Comparison |
| POST | `/api/repair` | 修复 RTL | Repair |

---

## 6. 加固策略说明

工具链内置 13 种加固策略，按面积开销与可靠性等级分类如下。

### 6.1 策略一览表

| 策略名称 | 描述 | 面积开销 | 可靠性等级（1-5） |
|---------|------|:-------:|:----------------:|
| `tmr` | 三模冗余（Triple Modular Redundancy） | 3.0× | 5 |
| `ecc` | 纠错码（SECDED，单错纠正双错检测） | 1.4× | 4 |
| `dice` | 双互锁存储单元（Dual Interlocked Storage Cell） | 2.5× | 5 |
| `parity` | 奇偶校验（Parity Check） | 0.03× | 2 |
| `tmr_ecc` | TMR + ECC 混合加固 | 4.4× | 5 |
| `cnt_comp` | 计数器比较器（Counter Comparator） | 0.1× | 3 |
| `watchdog` | 看门狗定时器（Watchdog Timer） | 0.5× | 2 |
| `one_hot_fsm` | 独热码状态机（One-Hot FSM） | 1.1× | 4 |
| `bch_ecc` | BCH 纠错码（多比特纠错） | 1.8× | 4 |
| `crc` | 循环冗余校验（Cyclic Redundancy Check） | 0.3× | 3 |
| `tmr_dice` | TMR + DICE 混合加固 | 5.5× | 5 |
| `scrubbing` | 存储器清洗（Memory Scrubbing） | 0.2× | 3 |
| `interleaving` | 位交织（Bit Interleaving） | 0.1× | 2 |

### 6.2 策略选择建议

- **最高可靠性需求**（航空航天、汽车安全关键）：`tmr_dice`、`tmr_ecc`、`tmr`
- **中等可靠性 + 低面积**（工业控制）：`dice`、`ecc`、`bch_ecc`
- **低成本检测**（消费电子）：`parity`、`crc`、`interleaving`
- **FSM 保护**：`one_hot_fsm`
- **计数器保护**：`cnt_comp`
- **存储器保护**：`scrubbing` + `ecc`
- **总线保护**：`parity` 或 `crc`

### 6.3 策略属性说明

- **面积开销**：相对于原始设计的面积倍数（如 3.0× 表示面积增加 200%）
- **可靠性等级**：1=最低，5=最高，反映抗单粒子翻转（SEU）能力
- **延迟开销**：0=无额外延迟，1=单周期延迟，2=多周期延迟
- **功耗开销**：相对于原始设计的功耗倍数

---

## 7. Docker 部署

### 7.1 Dockerfile 说明

仓库根目录提供 `Dockerfile`，基于 `python:3.10-slim` 构建，内置：
- 系统依赖：`gcc`、`g++`、`libreadline-dev`、`bison`、`flex` 等
- Yosys：通过 oss-cad-suite 安装（版本 2024-01-01）
- Python 依赖：通过 `requirements.txt` 安装
- 默认启动命令：`python api_server.py`
- 暴露端口：8000
- 健康检查：每 30 秒一次

### 7.2 构建与运行

```bash
# 构建镜像
docker build -t rtl-hardening-toolchain .

# 运行 API 服务（默认）
docker run -d --name hardening-api -p 8000:8000 rtl-hardening-toolchain

# 交互式运行（用于命令行工具）
docker run -it --rm -v $(pwd):/app rtl-hardening-toolchain bash

# 运行加固管线
docker run --rm -v $(pwd)/designs:/designs rtl-hardening-toolchain \
    python graph_pipeline.py --harden /designs/target.v --hardening-strategy tmr
```

### 7.3 环境变量配置

通过 `-e` 参数传递环境变量：

```bash
docker run -d -p 8000:8000 \
    -e OPENAI_API_KEY=sk-your-key \
    -e OPENAI_MODEL=gpt-4 \
    -e OPENAI_BASE_URL=https://api.openai.com/v1 \
    -e CONFIG__INFERENCE__THRESHOLD=0.1 \
    -e CONFIG__TRAIN__DEVICE=cpu \
    rtl-hardening-toolchain
```

**支持的环境变量：**

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENAI_API_KEY` | OpenAI API Key | - |
| `OPENAI_MODEL` | 使用的模型名称 | gpt-4 |
| `OPENAI_BASE_URL` | API 基础 URL | https://api.openai.com/v1 |
| `CONFIG__<SECTION>__<KEY>` | 覆盖配置项（见 [8. 配置文件](#8-配置文件)） | - |
| `PYTHONUNBUFFERED` | Python 输出不缓冲 | 1 |

**配置覆盖示例：**
```bash
# 等价于 config.set('inference.threshold', 0.1)
CONFIG__INFERENCE__THRESHOLD=0.1

# 等价于 config.set('train.epochs', 500)
CONFIG__TRAIN__EPOCHS=500
```

### 7.4 Docker Compose 示例

```yaml
version: '3.8'
services:
  hardening-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - CONFIG__INFERENCE__THRESHOLD=0.05
    volumes:
      - ./data:/app/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 3s
      retries: 3
```

---

## 8. 配置文件

### 8.1 .env 配置说明

`.env` 文件用于存储 OpenAI API 凭据，位于工具目录下。可参考 `.env.example` 模板。

**文件格式：**
```ini
# OpenAI API Configuration
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_MODEL=gpt-4
OPENAI_BASE_URL=https://api.openai.com/v1
```

**字段说明：**

| 字段 | 说明 | 必填 |
|------|------|------|
| `OPENAI_API_KEY` | OpenAI API Key，必须以 `sk-` 开头 | 是（使用 OpenAI 后端时） |
| `OPENAI_MODEL` | 模型名称（如 `gpt-4`、`gpt-3.5-turbo`） | 否 |
| `OPENAI_BASE_URL` | API 基础 URL，可指向兼容接口 | 否 |

**生成方式：**
- 运行 `python setup_api.py` 交互式生成
- 或手动复制 `.env.example` 为 `.env` 并编辑

**加载优先级：**
1. 显式传入的 Key（最高）
2. 环境变量 `OPENAI_API_KEY`
3. `.env` 文件中的值

### 8.2 config.yaml 说明

`config.yaml` 是工具链的主配置文件，覆盖 `config.py` 中的默认值。

**完整配置示例：**
```yaml
# 路径配置
paths:
  data_dir: "data/"
  models_dir: "data/models/"
  logs_dir: "logs/"

# 训练配置
train:
  model: "SAGE3"              # 模型架构
  hidden_channels: 128        # 隐藏层维度
  epochs: 200                 # 训练轮数
  patience: 50                # 早停耐心值
  batch_size: 32              # 批大小
  lr: 0.001                   # 学习率
  device: "cpu"               # 设备（cpu/cuda）
  loss: "FocalLoss"            # 损失函数
  focal_alpha: 0.977          # Focal Loss alpha
  focal_gamma: 2.0            # Focal Loss gamma
  use_pi_weighting: true      # 启用 PI 加权
  pi_weight: 10.0             # PI 权重

# 推理配置
inference:
  threshold: 0.05             # 脆弱性阈值
  device: "cpu"
  benchmark_runs: 10          # 基准测试次数

# 图管线配置
graph:
  target_features: 12         # 目标特征维度
  generate_labels: true       # 生成标签
  label_mode: "prob_decay"    # 标签模式

# 日志配置
logging:
  level: "INFO"
  file: "pipeline.log"
  max_size_mb: 10
  backup_count: 3
  console_output: true
```

**环境变量覆盖：** 使用 `CONFIG__<SECTION>__<KEY>` 格式，例如 `CONFIG__TRAIN__EPOCHS=500`。

### 8.3 pytest.ini 说明

`pytest.ini` 配置测试运行行为：

```ini
[pytest]
testpaths = .
pythonpath = .
addopts = -v --tb=short --ignore=_test_complex_repair.py --ignore=...
```

**说明：**
- `testpaths = .`：测试文件搜索路径为当前目录
- `pythonpath = .`：将当前目录加入 Python 路径
- `addopts`：默认选项，`-v` 详细输出，`--tb=short` 简短回溯
- `--ignore=...`：忽略以 `_` 开头的调试/临时脚本（这些不是正式测试）

---

## 9. 测试

### 9.1 运行测试

```bash
# 运行全部测试（使用 pytest.ini 配置）
pytest

# 运行特定测试文件
pytest test_regression_suite.py

# 运行特定测试类或函数
pytest test_regression_suite.py::TestTMRStrategies::test_basic_tmr

# 详细输出
pytest -v

# 只运行快速测试
pytest test_regression_suite.py --quick

# 生成测试报告
pytest --junitxml=test_report.xml
```

### 9.2 回归测试套件

`test_regression_suite.py` 是核心回归测试，覆盖：

1. TMR 加固策略验证
2. ECC 加固策略验证
3. DICE 加固策略验证
4. Parity 加固策略验证
5. 多策略组合验证
6. 设计错误分析
7. AST 修复
8. Yosys 综合验证

```bash
# 运行完整回归测试
python test_regression_suite.py

# 快速模式
python test_regression_suite.py --quick

# 仅测试特定策略
python test_regression_suite.py --strategy tmr
```

### 9.3 测试覆盖范围

| 测试文件 | 覆盖范围 |
|---------|---------|
| `test_regression_suite.py` | 全策略回归测试、Yosys 验证 |
| `test_harden_strategies.py` | 单策略加固正确性 |
| `test_harden_pipeline.py` | 加固管线端到端 |
| `test_integration.py` | 模块集成测试 |
| `test_integration_pipeline.py` | 管线集成测试 |
| `test_p0_features.py` ~ `test_p3_features.py` | 分级特征工程测试 |
| `test_int8_quantization.py` | int8 量化测试 |
| `test_int16_quantization.py` | int16 量化测试 |
| `test_qat_int8.py` | 量化感知训练测试 |
| `test_fpga_deploy.py` | FPGA 部署测试 |
| `test_gui_comprehensive.py` | Web GUI 综合测试 |
| `test_hierarchical_registers.py` | 层次化寄存器测试 |
| `test_module_strategy_allocation.py` | 模块策略分配测试 |

### 9.4 CI/CD 集成

使用 `deploy_ci.py` 进行 CI 自动化部署：

```bash
# 模拟运行（不提交 Git）
python deploy_ci.py --dry-run

# 快速模式
python deploy_ci.py --quick

# 指定分支并生成报告
python deploy_ci.py --branch main --report-dir reports/
```

详见 `DEPLOY_CI_USER_GUIDE.md`。

---

## 10. FAQ

### Q1：模型未找到，提示 "Model not found" 怎么办？

**A：** 工具链默认在 `data/models/local_best_model.pt` 查找模型。解决方法：

1. 确认模型文件存在：
   ```bash
   ls data/models/local_best_model.pt
   ```
2. 若不存在，先训练模型：
   ```bash
   python _train_local.py
   ```
3. 或通过 `--model` 参数指定其他路径：
   ```bash
   python gnn_inference.py --blif design.blif --model /path/to/your_model.pt
   ```

### Q2：Yosys 未安装或综合失败怎么办？

**A：** Yosys 是可选依赖，但综合与形式验证需要它。解决方案：

1. **安装 oss-cad-suite**（推荐）：下载并解压到项目根目录 `tools/oss-cad-suite/` 下，工具链会自动识别。
2. **使用 Docker**：无需本地安装，工具链会自动调用 `ghcr.io/yosyshq/yosys:latest` 镜像。确保 Docker 已安装且运行。
3. **跳过 Yosys 验证**：使用 `--no-ast-repair` 或不启用 `--docker-verify`，但会降低加固可信度。
4. **Windows 用户**：若遇到 DLL 问题，确保 oss-cad-suite 的 `bin` 和 `lib` 目录已加入 PATH。

### Q3：如何使用 OpenAI GPT 生成加固代码而不是 Mock LLM？

**A：** 配置 OpenAI API 后指定 `openai` 后端：

1. 运行配置脚本：
   ```bash
   python setup_api.py
   ```
   按提示输入 API Key（以 `sk-` 开头）。

2. 在加固时指定后端：
   ```bash
   python graph_pipeline.py --harden target.v --llm-backend openai
   ```

3. 或在 Python API 中：
   ```python
   from rag_integration import RAGEngine
   engine = RAGEngine(llm_backend='openai')
   ```

若未配置 API Key，工具链会自动降级为 `mock` 后端（生成模板化加固代码，用于离线测试）。

### Q4：大规模设计（10万+节点）推理时内存溢出怎么办？

**A：** 使用 `large_scale_inference.py` 的分块与半精度推理：

1. **先估算内存需求**：
   ```bash
   python large_scale_inference.py --input big_design.blif --estimate-only
   ```

2. **分块推理**（默认 chunk_size=10000）：
   ```bash
   python large_scale_inference.py --input big_design.blif --chunk-size 5000
   ```

3. **半精度推理**（显存减半）：
   ```bash
   python large_scale_inference.py --input big_design.blif --half-precision
   ```

4. **渐进式推理**（只处理前 N 个节点）：
   ```bash
   python large_scale_inference.py --input big_design.blif --max-nodes 50000
   ```

5. **图优化**（去除孤立节点、合并冗余边）：
   ```bash
   python large_scale_inference.py --input big_design.blif --optimize-graph
   ```

### Q5：如何选择合适的加固策略？

**A：** 根据应用场景的可靠性需求与面积预算选择：

1. **使用 API 自动推荐**：
   ```bash
   curl -X POST http://localhost:8000/api/compare \
     -H "Content-Type: application/json" \
     -d '{"rtl_code": "...", "strategies": ["tmr","ecc","dice","parity"]}'
   ```

2. **参考策略表**（见 [6. 加固策略说明](#6-加固策略说明)）：
   - 航空航天/汽车安全关键：`tmr_dice`、`tmr_ecc`
   - 工业控制：`dice`、`ecc`
   - 消费电子（低成本）：`parity`、`crc`
   - FSM 保护：`one_hot_fsm`
   - 存储器保护：`scrubbing` + `ecc`

3. **使用 GNN 指导**：先运行 `gnn_inference.py` 识别脆弱节点，再针对脆弱信号应用高可靠性策略，非脆弱信号应用低成本策略（选择性加固）。

### Q6：API 服务无法启动，提示 "FastAPI not available"？

**A：** 安装 FastAPI 与 Uvicorn：

```bash
pip install fastapi uvicorn pydantic
```

若已安装仍报错，检查 Python 版本是否 ≥ 3.10：
```bash
python --version
```

### Q7：加固后的 RTL 无法通过 Yosys 综合怎么办？

**A：** 工具链内置 AST 修复迭代机制，会自动尝试修复语法错误。若仍失败：

1. 增加修复迭代次数：
   ```bash
   python graph_pipeline.py --harden target.v --max-repair-iter 10
   ```
2. 启用 Docker Yosys 验证获取详细错误：
   ```bash
   python graph_pipeline.py --harden target.v --docker-verify
   ```
3. 查看生成的修复报告（`*_repair_report.md`）定位问题。
4. 尝试切换加固策略（如从 `tmr_dice` 降级为 `tmr`）。

### Q8：如何在 GPU 上加速推理？

**A：**

1. 确认 CUDA 可用：
   ```python
   import torch
   print(torch.cuda.is_available())
   ```

2. 安装 GPU 版 PyTorch（参考 [pytorch.org](https://pytorch.org/get-started/locally/)）。

3. 指定 CUDA 设备：
   ```bash
   python gnn_inference.py --blif design.blif  # 自动检测
   # 或
   python large_scale_inference.py --input design.blif --device cuda --half-precision
   ```

4. 在配置中设置：
   ```yaml
   inference:
     device: "cuda"
   ```
   或环境变量：`CONFIG__INFERENCE__DEVICE=cuda`

---

## 附录

### A. 相关文档

| 文档 | 说明 |
|------|------|
| `DEPLOY_CI_USER_GUIDE.md` | CI 自动化部署详细指南 |
| `data/fpga/FINAL_DEPLOYMENT_GUIDE.md` | FPGA 部署指南 |
| `data/fpga/FINAL_MODEL_EVALUATION_REPORT.md` | 模型评估报告 |
| `data/fpga/HARDWARE_RESOURCE_AND_LATENCY_REPORT.md` | 硬件资源与延迟报告 |
| `QAT_VS_INT16_COMPARISON_REPORT.md` | 量化方案对比报告 |

### B. 目录结构概览

```
formal_test/
├── gnn_inference.py          # GNN 脆弱性推理
├── rag_integration.py        # RAG-LLM 加固
├── auto_repair.py            # 自动修复
├── graph_pipeline.py         # 综合管线
├── api_server.py             # REST API 服务
├── web_gui.py                # Web GUI
├── setup_api.py              # API 配置
├── large_scale_inference.py  # 大规模推理
├── model_compression.py      # 模型压缩
├── config.py / config.yaml   # 配置管理
├── Dockerfile                # Docker 部署
├── pytest.ini                # 测试配置
├── .env.example              # 环境变量模板
├── data/                     # 数据与模型
│   ├── models/               # 训练好的模型
│   ├── blifs/                # BLIF 设计文件
│   ├── aigs/                 # AIG 设计文件
│   ├── onnx/                 # ONNX 模型
│   └── fpga/                 # FPGA 部署资源
├── test_*.py                 # 测试套件
└── _*.py                     # 内部脚本（训练/调试）
```

### C. 联系与反馈

如遇本手册未覆盖的问题，请参考：
- 运行 `python <script>.py --help` 查看最新参数
- 查看 `logs/pipeline.log` 排查错误
- 参考 `DEPLOY_CI_USER_GUIDE.md` 与各报告文档
