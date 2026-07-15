#!/usr/bin/env python3
"""
sva_inserter.py — SystemVerilog Assertion (SVA) 自动插入模块

在加固后的 RTL 代码中自动插入 SystemVerilog 断言，用于验证加固逻辑的正确性。

核心功能：
  1. TMR 断言 — 验证三模冗余和投票器逻辑
  2. ECC 断言 — 验证纠错码编码/解码逻辑
  3. DICE 断言 — 验证双互锁存储单元
  4. 通用断言 — 复位、时钟、边界检查等
  5. 自动检测 — 扫描 RTL 中的加固模式并插入对应断言

设计原则：
  - 非侵入式 — 不修改原始逻辑，仅添加断言模块
  - 可配置 — 支持不同断言类型和覆盖级别
  - 可验证 — 生成的断言可被形式验证工具使用
  - 模块化 — 每个断言类型独立实现

用法:
    from sva_inserter import SVASetter

    sva = SVASetter()

    # 插入所有类型的断言
    rtl_with_sva = sva.insert_all(rtl_code, design_info)

    # 仅插入 TMR 断言
    rtl_with_tmr = sva.insert_tmr_assertions(rtl_code, design_info)
"""

import os
import re
import json
import time
from typing import Dict, List, Optional, Tuple, Any

try:
    from logger import logger
except ImportError:
    import logging
    logger = logging.getLogger("sva_inserter")


# ============================================================================
# Assertion Templates
# ============================================================================

TMR_ASSERTION_TEMPLATE = """
// ── TMR 冗余验证断言 ──
module sva_tmr_checker_{module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    {signal_declarations}
);

    // 断言: 三个副本在稳定状态下的值应该一致
    // (允许在切换周期内短暂不一致)
    property tmr_stability;
        @(posedge clk) disable iff (!rst_n)
            ($stable({copy_a}) && $stable({copy_b}) && $stable({copy_c}))
            |=> ({copy_a} == {copy_b}) && ({copy_b} == {copy_c});
    endproperty
    assert property (tmr_stability)
        else $error("[SVA] TMR stability violation: copies diverged");

    // 断言: 投票器输出应该是三个副本的多数表决结果
    property tmr_voter_correct;
        @(posedge clk) disable iff (!rst_n)
            ({voter_out} == ({copy_a} & {copy_b}) | ({copy_a} & {copy_c}) | ({copy_b} & {copy_c}));
    endproperty
    assert property (tmr_voter_correct)
        else $error("[SVA] TMR voter output mismatch");

    // 断言: 检测到单粒子翻转后应该能恢复
    property tmr_recovery;
        @(posedge clk) disable iff (!rst_n)
            ($past({copy_a}, 1) !== {copy_a}) |=>
            (({copy_a} == {copy_b}) || ({copy_a} == {copy_c}));
    endproperty
    assert property (tmr_recovery)
        else $warning("[SVA] TMR recovery warning: SEU detected");

endmodule
"""

ECC_ASSERTION_TEMPLATE = """
// ── ECC 纠错码验证断言 ──
module sva_ecc_checker_{module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    {signal_declarations}
);

    // 断言: 编码后的数据在无错误情况下应能正确解码还原
    property ecc_encode_decode_roundtrip;
        @(posedge clk) disable iff (!rst_n)
            ({encode} == 1'b1 && $stable({data_in}))
            |=> ##1 ({data_out} == $past({data_in}));
    endproperty
    assert property (ecc_encode_decode_roundtrip)
        else $error("[SVA] ECC roundtrip failure");

    // 断言: 单比特错误应能被检测并纠正
    property ecc_single_bit_correction;
        @(posedge clk) disable iff (!rst_n)
            ({error_flag} == 1'b1) |=> ##1 ({uncorrectable} == 1'b0);
    endproperty
    assert property (ecc_single_bit_correction)
        else $error("[SVA] ECC single-bit error not correctable");

    // 断言: 多比特错误应被标记为不可纠正
    property ecc_multi_bit_detection;
        @(posedge clk) disable iff (!rst_n)
            ({uncorrectable} == 1'b1) |-> ({error_flag} == 1'b1);
    endproperty
    assert property (ecc_multi_bit_detection)
        else $error("[SVA] ECC multi-bit error without error flag");

endmodule
"""

DICE_ASSERTION_TEMPLATE = """
// ── DICE 双互锁存储单元验证断言 ──
module sva_dice_checker_{module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    {signal_declarations}
);

    // 断言: DICE 单元的两个节点应该总是互补
    property dice_complementary;
        @(posedge clk) disable iff (!rst_n)
            ({node_q0} === ~{node_q1});
    endproperty
    assert property (dice_complementary)
        else $error("[SVA] DICE nodes not complementary");

    // 断言: 复位后应进入已知状态
    property dice_reset_state;
        @(posedge clk)
            ($fell(rst_n)) |=> ##1 ({node_q0} === 1'b0 && {node_q1} === 1'b1);
    endproperty
    assert property (dice_reset_state)
        else $error("[SVA] DICE reset state violation");

    // 断言: 翻转后状态应该稳定
    property dice_state_stability;
        @(posedge clk) disable iff (!rst_n)
            $stable({node_q0}) && $stable({node_q1});
    endproperty
    assert property (dice_state_stability)
        else $warning("[SVA] DICE state instability");

endmodule
"""

GENERIC_ASSERTION_TEMPLATE = """
// ── 通用设计验证断言 ──
module sva_generic_checker_{module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    {signal_declarations}
);

    // 断言: 复位信号应为低有效
    property reset_active_low;
        @(posedge clk)
            (rst_n === 1'b0) |-> $past(rst_n, 1) !== 1'b0 || $stable(rst_n);
    endproperty
    assert property (reset_active_low)
        else $warning("[SVA] Reset assertion violation");

    // 断言: 时钟应保持稳定频率（检测毛刺）
    property clock_no_glitch;
        @(posedge clk)
            $onehot0({clk});
    endproperty
    assert property (clock_no_glitch)
        else $error("[SVA] Clock glitch detected");

    // 断言: 输出信号应在复位后有效
    property output_valid_after_reset;
        @(posedge clk)
            ($rose(rst_n)) |=> ##2 ({output_valid} === 1'b1);
    endproperty
    assert property (output_valid_after_reset)
        else $warning("[SVA] Output not valid after reset");

    // 断言: 计数器不应溢出
    {counter_checks}

endmodule
"""

COUNTER_OVERFLOW_CHECK = """
    // 断言: 计数器 {counter_name} 不应溢出
    property counter_{counter_name}_no_overflow;
        @(posedge clk) disable iff (!rst_n)
            ({counter_name} == {max_value}) |=> ({counter_name} !== {max_value} + 1);
    endproperty
    assert property (counter_{counter_name}_no_overflow)
        else $error("[SVA] Counter {counter_name} overflow");
"""


# ============================================================================
# SVASetter
# ============================================================================

class SVASetter:
    """SVA 断言插入器。

    在加固后的 RTL 代码中自动插入 SystemVerilog 断言，
    用于验证加固逻辑的正确性。
    """

    def __init__(
        self,
        assertion_types: List[str] = None,
        coverage_level: str = 'full',
        insert_after_module: bool = True,
    ):
        """初始化断言插入器。

        Args:
            assertion_types: 要插入的断言类型列表
                ('tmr', 'ecc', 'dice', 'generic')
            coverage_level: 覆盖级别 ('basic', 'medium', 'full')
            insert_after_module: 是否在原模块后插入断言模块（而非内部）
        """
        self.assertion_types = assertion_types or ['tmr', 'ecc', 'dice', 'generic']
        self.coverage_level = coverage_level.lower()
        self.insert_after_module = insert_after_module

    def insert_all(
        self,
        rtl_code: str,
        design_info: Optional[Dict] = None,
    ) -> str:
        """插入所有启用的断言类型。

        Args:
            rtl_code: RTL 代码字符串
            design_info: 设计信息（包含加固策略等）

        Returns:
            插入断言后的 RTL 代码
        """
        logger.print(f"  [SVA] Inserting SVA assertions (types={self.assertion_types})")

        result = rtl_code

        if 'tmr' in self.assertion_types:
            result = self.insert_tmr_assertions(result, design_info)

        if 'ecc' in self.assertion_types:
            result = self.insert_ecc_assertions(result, design_info)

        if 'dice' in self.assertion_types:
            result = self.insert_dice_assertions(result, design_info)

        if 'generic' in self.assertion_types:
            result = self.insert_generic_assertions(result, design_info)

        return result

    def insert_tmr_assertions(
        self,
        rtl_code: str,
        design_info: Optional[Dict] = None,
    ) -> str:
        """插入 TMR 验证断言。

        Args:
            rtl_code: RTL 代码字符串
            design_info: 设计信息

        Returns:
            插入 TMR 断言后的 RTL 代码
        """
        tmr_patterns = [
            r'(copy_[abc])\s*<=|(reg_[012])\s*<=|(data_[abc])\s*<=',
        ]

        copies = set()
        for pattern in tmr_patterns:
            for match in re.finditer(pattern, rtl_code):
                for g in match.groups():
                    if g:
                        copies.add(g)

        if len(copies) < 3:
            logger.print(f"  [SVA]   No TMR copies detected, skipping TMR assertions")
            return rtl_code

        copy_list = sorted(copies)[:3]
        voter_match = re.search(r'(voter_out|tmr_out|majority_out)\s*=', rtl_code)
        voter_out = voter_match.group(1) if voter_match else copy_list[0] + '_voted'

        signal_declarations = self._build_signal_declarations(
            rtl_code, [*copy_list, voter_out], design_info
        )

        module_name = self._extract_module_name(rtl_code) or 'unknown'

        assertion_module = TMR_ASSERTION_TEMPLATE.format(
            module_name=module_name,
            signal_declarations=signal_declarations,
            copy_a=copy_list[0],
            copy_b=copy_list[1],
            copy_c=copy_list[2],
            voter_out=voter_out,
        )

        logger.print(f"  [SVA]   Inserted TMR assertions for {len(copies)} copies")
        return self._insert_module(rtl_code, assertion_module)

    def insert_ecc_assertions(
        self,
        rtl_code: str,
        design_info: Optional[Dict] = None,
    ) -> str:
        """插入 ECC 验证断言。

        Args:
            rtl_code: RTL 代码字符串
            design_info: 设计信息

        Returns:
            插入 ECC 断言后的 RTL 代码
        """
        ecc_signals = {}

        for sig_name in ['data_in', 'data_out', 'encode', 'error_flag', 'uncorrectable']:
            if sig_name in rtl_code:
                ecc_signals[sig_name] = sig_name

        if len(ecc_signals) < 3:
            logger.print(f"  [SVA]   No ECC signals detected, skipping ECC assertions")
            return rtl_code

        signal_declarations = self._build_signal_declarations(
            rtl_code, list(ecc_signals.values()), design_info
        )

        module_name = self._extract_module_name(rtl_code) or 'unknown'

        assertion_module = ECC_ASSERTION_TEMPLATE.format(
            module_name=module_name,
            signal_declarations=signal_declarations,
            **ecc_signals,
        )

        logger.print(f"  [SVA]   Inserted ECC assertions")
        return self._insert_module(rtl_code, assertion_module)

    def insert_dice_assertions(
        self,
        rtl_code: str,
        design_info: Optional[Dict] = None,
    ) -> str:
        """插入 DICE 验证断言。

        Args:
            rtl_code: RTL 代码字符串
            design_info: 设计信息

        Returns:
            插入 DICE 断言后的 RTL 代码
        """
        dice_patterns = [
            r'(node_[qQ][01])\s*<=',
            r'(dice_[01])\s*<=',
            r'(latch_[ab])\s*<=',
        ]

        nodes = set()
        for pattern in dice_patterns:
            for match in re.finditer(pattern, rtl_code):
                if match.group(1):
                    nodes.add(match.group(1))

        if len(nodes) < 2:
            logger.print(f"  [SVA]   No DICE nodes detected, skipping DICE assertions")
            return rtl_code

        node_list = sorted(nodes)[:2]

        signal_declarations = self._build_signal_declarations(
            rtl_code, node_list, design_info
        )

        module_name = self._extract_module_name(rtl_code) or 'unknown'

        assertion_module = DICE_ASSERTION_TEMPLATE.format(
            module_name=module_name,
            signal_declarations=signal_declarations,
            node_q0=node_list[0],
            node_q1=node_list[1],
        )

        logger.print(f"  [SVA]   Inserted DICE assertions for {len(nodes)} nodes")
        return self._insert_module(rtl_code, assertion_module)

    def insert_generic_assertions(
        self,
        rtl_code: str,
        design_info: Optional[Dict] = None,
    ) -> str:
        """插入通用设计验证断言。

        Args:
            rtl_code: RTL 代码字符串
            design_info: 设计信息

        Returns:
            插入通用断言后的 RTL 代码
        """
        counter_pattern = re.compile(r'reg\s+(?:\[[^\]]+\])?\s*(\w+)\s*;')
        counters = []
        for match in counter_pattern.finditer(rtl_code):
            name = match.group(1)
            if name.lower() not in ('clk', 'rst_n', 'rst') and \
               not name.lower().endswith(('_in', '_out', '_en', '_valid')):
                counters.append(name)

        counter_checks = ""
        for cnt in counters[:5]:
            counter_checks += COUNTER_OVERFLOW_CHECK.format(
                counter_name=cnt,
                max_value='32\'d4294967295',
            )

        signals_needed = ['rst_n', 'clk']
        if 'output_valid' in rtl_code:
            signals_needed.append('output_valid')

        signal_declarations = self._build_signal_declarations(
            rtl_code, signals_needed, design_info
        )

        module_name = self._extract_module_name(rtl_code) or 'unknown'

        assertion_module = GENERIC_ASSERTION_TEMPLATE.format(
            module_name=module_name,
            signal_declarations=signal_declarations,
            counter_checks=counter_checks,
            output_valid='output_valid' if 'output_valid' in rtl_code else '1\'b1',
        )

        logger.print(f"  [SVA]   Inserted generic assertions (counters={len(counters)})")
        return self._insert_module(rtl_code, assertion_module)

    def _extract_module_name(self, rtl_code: str) -> Optional[str]:
        """提取模块名称。"""
        match = re.search(r'module\s+(\w+)\s*', rtl_code)
        return match.group(1) if match else None

    def _build_signal_declarations(
        self,
        rtl_code: str,
        signal_names: List[str],
        design_info: Optional[Dict],
    ) -> str:
        """构建信号声明列表。"""
        declarations = []
        width = design_info.get('signal_width', 8) if design_info else 8

        for sig in signal_names:
            if sig in ['clk', 'rst_n']:
                declarations.append(f"    input  wire                     {sig},")
            else:
                declarations.append(f"    input  wire [{width-1}:0]       {sig},")

        return '\n'.join(declarations).rstrip(',')

    def _insert_module(self, rtl_code: str, assertion_module: str) -> str:
        """将断言模块插入到 RTL 代码中。"""
        if self.insert_after_module:
            end_module_pos = rtl_code.rfind('endmodule')
            if end_module_pos >= 0:
                insert_pos = end_module_pos + len('endmodule')
                return rtl_code[:insert_pos] + '\n\n' + assertion_module + rtl_code[insert_pos:]

        return rtl_code + '\n\n' + assertion_module

    def generate_bind_module(
        self,
        rtl_code: str,
        design_info: Optional[Dict] = None,
    ) -> str:
        """生成 bind 模块（将断言绑定到原模块）。

        Args:
            rtl_code: RTL 代码字符串
            design_info: 设计信息

        Returns:
            Bind 模块代码
        """
        module_name = self._extract_module_name(rtl_code) or 'DUT'
        bind_module = f"""
// ── Bind 模块: 将 SVA 断言绑定到设计 ──
bind {module_name} sva_tmr_checker_{module_name} sva_tmr(
    .clk(clk),
    .rst_n(rst_n)
);

bind {module_name} sva_generic_checker_{module_name} sva_generic(
    .clk(clk),
    .rst_n(rst_n)
);
"""
        return bind_module


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="SVA Assertion Inserter")
    parser.add_argument("--rtl", type=str, required=True, help="Path to RTL file")
    parser.add_argument("--output", type=str, help="Output path")
    parser.add_argument("--types", type=str, default="all",
                        help="Assertion types (tmr,ecc,dice,generic or all)")
    parser.add_argument("--coverage", type=str, default="full",
                        help="Coverage level (basic, medium, full)")
    args = parser.parse_args()

    if not os.path.isfile(args.rtl):
        logger.error(f"RTL file not found: {args.rtl}")
        return

    with open(args.rtl, "r", encoding="utf-8") as f:
        rtl_code = f.read()

    if args.types == 'all':
        assertion_types = ['tmr', 'ecc', 'dice', 'generic']
    else:
        assertion_types = [t.strip() for t in args.types.split(',')]

    sva = SVASetter(
        assertion_types=assertion_types,
        coverage_level=args.coverage,
    )

    result = sva.insert_all(rtl_code)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"SVA assertions inserted, output written to: {args.output}")
    else:
        print("\nResult with SVA assertions:")
        print("=" * 80)
        print(result)


if __name__ == "__main__":
    main()
