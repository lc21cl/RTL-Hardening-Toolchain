#!/usr/bin/env python3
"""api_server.py — REST API 服务

提供 RTL 加固工具链的 RESTful API 接口，支持远程调用和 CI/CD 集成。

使用 FastAPI 框架，提供以下端点：
  - POST /api/harden       — 对 RTL 代码进行加固
  - POST /api/vulnerability — 分析 RTL 代码的脆弱性
  - GET  /api/strategies    — 获取可用的加固策略列表
  - POST /api/compare       — 对比多种加固方案
  - GET  /api/health        — 健康检查
  - POST /api/repair        — 修复 RTL 代码语法错误

用法:
    python api_server.py                    # 开发模式
    uvicorn api_server:app --host 0.0.0.0 --port 8000  # 生产模式
"""

import os
import sys
import json
import time
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    print("FastAPI not available. Install with: pip install fastapi uvicorn")

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

try:
    from rag_integration import MockLLM
    from gnn_vulnerability import predict_vulnerability
    from auto_repair import AutoRepair
    from strategy_recommender import recommend_strategy
    from sdc_generator import generate_sdc_constraints, add_keep_attributes
    from logger import logger
except ImportError as e:
    print(f"Failed to import core modules: {e}")
    raise


class HardenRequest(BaseModel):
    rtl_code: str = Field(..., description="待加固的 RTL 代码")
    strategy: str = Field("tmr", description="加固策略 (tmr/ecc/dice/parity/tmr_ecc/cnt_comp/watchdog/one_hot_fsm/bch_ecc/crc/tmr_dice/scrubbing/interleaving)")
    parameters: Optional[Dict[str, Any]] = Field(None, description="策略参数")


class HardenResponse(BaseModel):
    success: bool = Field(..., description="操作是否成功")
    hardened_rtl: str = Field(..., description="加固后的 RTL 代码")
    strategy: str = Field(..., description="使用的加固策略")
    sdc_constraints: Optional[str] = Field(None, description="生成的 SDC 约束")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")


class VulnerabilityRequest(BaseModel):
    rtl_code: str = Field(..., description="待分析的 RTL 代码")


class VulnerabilityResponse(BaseModel):
    success: bool = Field(..., description="操作是否成功")
    results: Dict[str, Dict[str, Any]] = Field(..., description="脆弱性分析结果")
    summary: Dict[str, Any] = Field(..., description="分析摘要")


class CompareRequest(BaseModel):
    rtl_code: str = Field(..., description="待分析的 RTL 代码")
    strategies: List[str] = Field(..., description="要对比的策略列表")


class CompareResponse(BaseModel):
    success: bool = Field(..., description="操作是否成功")
    comparison: List[Dict[str, Any]] = Field(..., description="策略对比结果")
    recommendation: str = Field(..., description="推荐的策略")


class RepairRequest(BaseModel):
    rtl_code: str = Field(..., description="待修复的 RTL 代码")


class RepairResponse(BaseModel):
    success: bool = Field(..., description="操作是否成功")
    repaired_rtl: str = Field(..., description="修复后的 RTL 代码")
    errors_found: List[str] = Field(..., description="发现的错误")
    fixes_applied: List[str] = Field(..., description="应用的修复")


class HealthResponse(BaseModel):
    status: str = Field(..., description="服务状态")
    timestamp: str = Field(..., description="时间戳")
    version: str = Field(..., description="版本号")


if FASTAPI_AVAILABLE:
    app = FastAPI(
        title="RTL Hardening Tool Chain API",
        description="REST API for RTL hardening, vulnerability analysis, and code repair",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _mock_llm = MockLLM()


@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
async def health():
    return HealthResponse(
        status="healthy",
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        version="1.0.0",
    )


@app.get("/api/strategies", tags=["Strategies"])
async def get_strategies():
    strategies = [
        {"name": "tmr", "description": "Triple Modular Redundancy", "area_overhead": 3.0, "reliability": 5},
        {"name": "ecc", "description": "Error Correcting Code (SECDED)", "area_overhead": 1.4, "reliability": 4},
        {"name": "dice", "description": "Dual Interlocked Storage Cell", "area_overhead": 2.5, "reliability": 5},
        {"name": "parity", "description": "Parity Check", "area_overhead": 0.03, "reliability": 2},
        {"name": "tmr_ecc", "description": "TMR with ECC", "area_overhead": 4.4, "reliability": 5},
        {"name": "cnt_comp", "description": "Counter Comparator", "area_overhead": 0.1, "reliability": 3},
        {"name": "watchdog", "description": "Watchdog Timer", "area_overhead": 0.5, "reliability": 2},
        {"name": "one_hot_fsm", "description": "One-Hot FSM", "area_overhead": 1.1, "reliability": 4},
        {"name": "bch_ecc", "description": "BCH Error Correcting Code", "area_overhead": 1.8, "reliability": 4},
        {"name": "crc", "description": "Cyclic Redundancy Check", "area_overhead": 0.3, "reliability": 3},
        {"name": "tmr_dice", "description": "TMR + DICE Hybrid", "area_overhead": 5.5, "reliability": 5},
        {"name": "scrubbing", "description": "Memory Scrubbing", "area_overhead": 0.2, "reliability": 3},
        {"name": "interleaving", "description": "Bit Interleaving", "area_overhead": 0.1, "reliability": 2},
    ]
    return {"strategies": strategies}


@app.post("/api/harden", response_model=HardenResponse, tags=["Hardening"])
async def harden(request: HardenRequest):
    try:
        prompt = f"Apply {request.strategy} hardening to the following RTL module:\n\n{request.rtl_code}"
        hardened_rtl = _mock_llm.generate(prompt)

        module_name = "hardened_top"
        mn_match = __import__('re').search(r'module\s+(\w+)', request.rtl_code)
        if mn_match:
            module_name = mn_match.group(1)

        sdc_content = generate_sdc_constraints(
            module_name=module_name,
            protected_signals=[],
            protected_modules=[module_name]
        )

        hardened_rtl = add_keep_attributes(hardened_rtl, [], [module_name])

        return HardenResponse(
            success=True,
            hardened_rtl=hardened_rtl,
            strategy=request.strategy,
            sdc_constraints=sdc_content,
            metadata={"tokens_used": len(hardened_rtl), "model": "MockLLM"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/vulnerability", response_model=VulnerabilityResponse, tags=["Vulnerability"])
async def analyze_vulnerability(request: VulnerabilityRequest):
    try:
        results = predict_vulnerability(request.rtl_code)

        if isinstance(results, dict):
            high_vuln = sum(1 for v in results.values()
                           if isinstance(v, dict) and v.get("vulnerability_score", 0) > 0.7)
            total = len(results)
        else:
            high_vuln = 0
            total = 0

        return VulnerabilityResponse(
            success=True,
            results=results if isinstance(results, dict) else {},
            summary={
                "high_vulnerability_count": high_vuln,
                "total_analyzed": total,
                "model": "GraphSAGE",
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/compare", response_model=CompareResponse, tags=["Comparison"])
async def compare_strategies(request: CompareRequest):
    try:
        _STRATEGY_PROPS = {
            'tmr': {'area_overhead': 3.0, 'reliability': 5, 'latency': 1, 'power_overhead': 3.0},
            'ecc': {'area_overhead': 1.4, 'reliability': 4, 'latency': 1, 'power_overhead': 1.5},
            'dice': {'area_overhead': 2.5, 'reliability': 5, 'latency': 0, 'power_overhead': 2.5},
            'parity': {'area_overhead': 0.03, 'reliability': 2, 'latency': 0, 'power_overhead': 0.1},
            'tmr_ecc': {'area_overhead': 4.4, 'reliability': 5, 'latency': 2, 'power_overhead': 4.5},
            'cnt_comp': {'area_overhead': 0.1, 'reliability': 3, 'latency': 0, 'power_overhead': 0.2},
            'watchdog': {'area_overhead': 0.5, 'reliability': 2, 'latency': 0, 'power_overhead': 0.3},
            'one_hot_fsm': {'area_overhead': 1.1, 'reliability': 4, 'latency': 0, 'power_overhead': 1.2},
            'bch_ecc': {'area_overhead': 1.8, 'reliability': 4, 'latency': 1, 'power_overhead': 1.8},
            'crc': {'area_overhead': 0.3, 'reliability': 3, 'latency': 0, 'power_overhead': 0.3},
            'tmr_dice': {'area_overhead': 5.5, 'reliability': 5, 'latency': 1, 'power_overhead': 5.5},
            'scrubbing': {'area_overhead': 0.2, 'reliability': 3, 'latency': 0, 'power_overhead': 0.15},
            'interleaving': {'area_overhead': 0.1, 'reliability': 2, 'latency': 0, 'power_overhead': 0.05},
        }

        comparison = []
        for strategy in request.strategies:
            props = _STRATEGY_PROPS.get(strategy, {})
            comparison.append({
                "strategy": strategy,
                "area_overhead": props.get("area_overhead", 0),
                "reliability": props.get("reliability", 0),
                "latency": props.get("latency", 0),
                "power_overhead": props.get("power_overhead", 0),
            })

        recommendation = recommend_strategy(request.rtl_code)

        return CompareResponse(
            success=True,
            comparison=comparison,
            recommendation=recommendation,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/repair", response_model=RepairResponse, tags=["Repair"])
async def repair(request: RepairRequest):
    try:
        repairer = AutoRepair()
        result = repairer.run(request.rtl_code)

        return RepairResponse(
            success=result.get("success", False),
            repaired_rtl=result.get("final_rtl", request.rtl_code),
            errors_found=result.get("errors_found", []),
            fixes_applied=result.get("fixes_applied", []),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    if FASTAPI_AVAILABLE:
        uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
    else:
        print("FastAPI not installed. Please install with:")
        print("  pip install fastapi uvicorn")
