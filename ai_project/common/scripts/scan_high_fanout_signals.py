"""
高扇出信号扫描与加固建议工具

扫描 Verilog/SystemVerilog 项目中的所有信号，识别高扇入/扇出信号，
并根据信号特征推荐相应的抗辐射加固策略（TMR、ECC、Parity 等）。

用法:
    python scan_high_fanout_signals.py [--threshold THRESHOLD] [--dir DIR] [--output OUTPUT] [--include-hardened]
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


# ============================================================
# 数据结构定义
# ============================================================

@dataclass
class SignalInfo:
    """单个信号的解析信息"""
    name: str               # 信号名
    width: int = 1          # 位宽（默认为 1）
    file_path: str = ""     # 所在文件
    line_no: int = 0        # 声明行号
    fan_in: int = 0         # 扇入计数
    fan_out: int = 0        # 扇出计数
    is_hardened: bool = False  # 是否已加固
    strategy: str = ""      # 推荐策略


# ============================================================
# 1. 文件发现与过滤
# ============================================================

def find_verilog_files(root_dir: str) -> List[str]:
    """
    递归扫描目录下所有 .v 和 .sv 文件，跳过 testbench 文件。

    跳过规则：
    - 文件路径中包含 'tb_' 前缀
    - 文件路径在 testbench 目录下（如 'tb', 'testbench', 'test'）
    """
    verilog_files = []
    tb_dirs = {"tb", "testbench", "testbench", "sim"}

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # 跳过 testbench 目录
        rel_path = os.path.relpath(dirpath, root_dir)
        top_dir = rel_path.split(os.sep)[0] if rel_path != "." else ""
        if top_dir.lower() in tb_dirs:
            continue

        for fname in filenames:
            if not (fname.endswith(".v") or fname.endswith(".sv")):
                continue
            # 跳过 tb_ 开头的文件
            if fname.startswith("tb_"):
                continue
            file_path = os.path.join(dirpath, fname)
            verilog_files.append(file_path)

    return sorted(verilog_files)


# ============================================================
# 2. 信号声明解析
# ============================================================

# 信号声明匹配模式：reg/wire + 可选位宽 + 信号名
SIGNAL_DECL_PATTERN = re.compile(
    r'(reg|wire)\s*(?:\[(\d+):(\d+)\])?\s*(\w+)\s*(?:;|\[)'
)

# 阻塞赋值 / 非阻塞赋值 LHS 匹配：在 <= 或 = 左侧的信号名
LHS_ASSIGN_PATTERN = re.compile(
    r'(?:(?<=\W)|^)(\w+)\s*(?:<=\s*|=)'
)

# 赋值 RHS 匹配：在 <= 或 = 右侧出现的信号名
RHS_ASSIGN_PATTERN = re.compile(
    r'(?:<=|=(?!\s*=))\s*([^;]+?)\s*(?:;|$)'
)

# case 表达式匹配
CASE_PATTERN = re.compile(
    r'\bcase\s*\(\s*(\w+)\s*\)'
)

# 信号名拆分（用于 RHS 中提取信号名）
RHS_TOKEN_PATTERN = re.compile(r'\b(\w+)\b')

# 加固模块名称特征
HARDENED_MODULE_PATTERN = re.compile(r'(tmr_voter|ecc_|dice_)', re.IGNORECASE)

# 实例化端口连接中 voter / ecc / dice 连接检测
HARDENED_PORT_PATTERN = re.compile(r'\.\w+\s*\(\s*\w*(voter|ecc_|dice_)\w*\s*\)', re.IGNORECASE)

# TMR 副本信号名模式：以 _0, _1, _2 结尾
TMR_COPY_PATTERN = re.compile(r'_\d$')


def parse_signal_width(msb: Optional[str], lsb: Optional[str]) -> int:
    """
    根据 MSB 和 LSB 计算位宽。

    Args:
        msb: 最高有效位（字符串或 None）
        lsb: 最低有效位（字符串或 None）

    Returns:
        位宽值，若无法计算则返回 1
    """
    if msb is None or lsb is None:
        return 1
    try:
        msb_val = int(msb)
        lsb_val = int(lsb)
        return abs(msb_val - lsb_val) + 1
    except ValueError:
        # 可能是宏定义（如 `InstAddrBus），无法直接计算
        return 1


def extract_declared_signals(content: str, file_path: str) -> Dict[str, SignalInfo]:
    """
    从文件内容中提取所有声明的 reg/wire 信号。

    Args:
        content: 文件内容
        file_path: 文件路径

    Returns:
        信号名 -> SignalInfo 的字典
    """
    signals: Dict[str, SignalInfo] = {}

    for match in SIGNAL_DECL_PATTERN.finditer(content):
        signal_type = match.group(1)    # reg 或 wire
        msb = match.group(2)            # 位宽 MSB
        lsb = match.group(3)            # 位宽 LSB
        sig_name = match.group(4)       # 信号名

        # 计算行号
        line_no = content[:match.start()].count('\n') + 1

        width = parse_signal_width(msb, lsb)

        if sig_name not in signals:
            signals[sig_name] = SignalInfo(
                name=sig_name,
                width=width,
                file_path=file_path,
                line_no=line_no,
            )
        else:
            # 同名信号取最大位宽（可能在不同位置声明）
            if width > signals[sig_name].width:
                signals[sig_name].width = width
                signals[sig_name].file_path = file_path
                signals[sig_name].line_no = line_no

    return signals


# ============================================================
# 3. 扇入/扇出分析
# ============================================================

def count_signal_activity(content: str, signals: Dict[str, SignalInfo]):
    """
    统计文件中每个信号的扇入（赋值左侧）和扇出（赋值右侧/case 表达式）。

    Args:
        content: 文件内容
        signals: 信号字典（会被原地更新 fan_in / fan_out）
    """
    # 统计扇入：出现在 <= 或 = 左侧
    for match in LHS_ASSIGN_PATTERN.finditer(content):
        lhs_name = match.group(1)
        if lhs_name in signals:
            signals[lhs_name].fan_in += 1

    # 统计扇出：出现在 <= 或 = 右侧
    for match in RHS_ASSIGN_PATTERN.finditer(content):
        rhs_expr = match.group(1)
        for token_match in RHS_TOKEN_PATTERN.finditer(rhs_expr):
            token = token_match.group(1)
            if token in signals:
                signals[token].fan_out += 1

    # 统计扇出：case 表达式中的信号
    for match in CASE_PATTERN.finditer(content):
        case_sig = match.group(1)
        if case_sig in signals:
            signals[case_sig].fan_out += 1


# ============================================================
# 4. 加固状态检测
# ============================================================

def is_signal_hardened_by_name(sig_name: str) -> bool:
    """
    通过信号名判断是否已加固（TMR 副本信号 _0, _1, _2）。

    Args:
        sig_name: 信号名

    Returns:
        是否已加固
    """
    return bool(TMR_COPY_PATTERN.search(sig_name))


def is_module_hardened(module_name: str) -> bool:
    """
    判断模块名是否表明已加固。

    Args:
        module_name: 模块名

    Returns:
        是否已加固模块
    """
    return bool(HARDENED_MODULE_PATTERN.search(module_name))


def is_port_connected_to_hardened(content: str) -> bool:
    """
    检查实例化端口连接是否连接到加固相关信号（voter / ecc / dice）。

    Args:
        content: 文件内容

    Returns:
        是否存在加固连接
    """
    return bool(HARDENED_PORT_PATTERN.search(content))


def check_hardening_status(signals: Dict[str, SignalInfo], file_content_map: Dict[str, str]):
    """
    批量检测所有信号的加固状态。

    Args:
        signals: 信号字典
        file_content_map: 文件路径 -> 内容 的映射
    """
    for sig_name, sig_info in signals.items():
        # 检查信号名是否包含 TMR 副本后缀
        if is_signal_hardened_by_name(sig_name):
            sig_info.is_hardened = True
            continue

        # 检查所在文件的端口连接是否涉及加固信号
        file_content = file_content_map.get(sig_info.file_path, "")
        if file_content and is_port_connected_to_hardened(file_content):
            sig_info.is_hardened = True
            continue

        # 检查所在文件的模块名是否包含加固特征
        module_names = re.findall(r'module\s+(\w+)', file_content)
        for mod_name in module_names:
            if is_module_hardened(mod_name):
                sig_info.is_hardened = True
                break


# ============================================================
# 5. 加固策略推荐
# ============================================================

# 自增/自减模式：<= expr + 1 或 <= expr - 1
CNT_COMP_PATTERN = re.compile(r'<=\s*\w+\s*[+]\s*\d|(?:\b\w+\s*\+\s*1\b)|(?:\b\w+\s*-\s*1\b)')

# 计数/状态机相关信号名模式
CNT_NAME_PATTERN = re.compile(r'(count|cnt|timer)', re.IGNORECASE)
STATE_NAME_PATTERN = re.compile(r'state', re.IGNORECASE)


def recommend_strategy(sig: SignalInfo, content: str) -> str:
    """
    根据信号特征推荐加固策略。

    优先级：
    1. 位宽 >= 16 → ECC (SECDED)
    2. 位宽 >= 8  → Parity
    3. 信号名含 count/cnt/timer → cnt_comp
    4. 信号名含 state → TMR_state
    5. 包含自增/自减模式 → cnt_comp
    6. 窄控制信号 (< 8) → Parity
    7. 默认 → TMR_reg

    Args:
        sig: 信号信息
        content: 文件内容（用于检测自增/自减模式）

    Returns:
        推荐的加固策略名称
    """
    # 位宽 >= 16 推荐 ECC
    if sig.width >= 16:
        return "ECC"

    # 位宽 >= 8 推荐 Parity
    if sig.width >= 8:
        return "Parity"

    # 含自增/自减模式 → cnt_comp
    if CNT_COMP_PATTERN.search(content):
        return "cnt_comp"

    # 信号名含 count/cnt/timer → cnt_comp
    if CNT_NAME_PATTERN.search(sig.name):
        return "cnt_comp"

    # 信号名含 state → TMR_state
    if STATE_NAME_PATTERN.search(sig.name):
        return "TMR_state"

    # 窄控制信号 → Parity
    if sig.width < 8:
        return "Parity"

    # 默认
    return "TMR_reg"


# ============================================================
# 6. 输出报告生成
# ============================================================

def generate_report(
    candidates: List[SignalInfo],
    hardened_signals: List[SignalInfo],
    scan_dir: str,
    threshold: int,
    total_signals: int,
    scan_files: List[str],
) -> str:
    """
    生成 Markdown 格式的报告。

    Args:
        candidates: 未加固的高扇出候选信号列表
        hardened_signals: 已加固的信号列表
        scan_dir: 扫描目录
        threshold: 扇入扇出阈值
        total_signals: 扫描信号总数
        scan_files: 扫描的文件列表

    Returns:
        Markdown 格式的完整报告文本
    """
    lines = []

    # 按活跃度降序排列
    candidates.sort(key=lambda s: s.fan_in + s.fan_out, reverse=True)

    lines.append("# 高扇出信号加固建议报告")
    lines.append("")
    lines.append("## 扫描配置")
    lines.append(f"- 扫描目录: {scan_dir}")
    lines.append(f"- 扇入扇出阈值: {threshold}")
    lines.append(f"- 扫描文件: {len(scan_files)} 个")
    lines.append("")
    lines.append("## 候选信号列表")
    lines.append("")
    lines.append(
        "| 优先级 | 信号名 | 位宽 | 扇入 | 扇出 | 活跃度 | 推荐策略 | 文件 | 行号 |"
    )
    lines.append(
        "|:------|:-------|:----:|:----:|:----:|:------:|:---------|:----|:----:|"
    )

    if not candidates:
        lines.append("| - | 未发现高扇出信号 | - | - | - | - | - | - | - |")
    else:
        for sig in candidates:
            activity = sig.fan_in + sig.fan_out
            if activity >= 10:
                priority = "🔴 高"
            elif activity >= 5:
                priority = "🟡 中"
            else:
                priority = "🟢 低"

            rel_path = os.path.relpath(sig.file_path, scan_dir) if sig.file_path else ""
            lines.append(
                f"| {priority} | {sig.name} | {sig.width} | {sig.fan_in} | "
                f"{sig.fan_out} | {activity} | {sig.strategy} | {rel_path} | {sig.line_no} |"
            )

    lines.append("")
    lines.append("## 已加固信号 (参考)")
    lines.append("")

    if not hardened_signals:
        lines.append("| - | 未发现已加固信号 | - | - | - | - | - | - | - |")
    else:
        lines.append(
            "| 优先级 | 信号名 | 位宽 | 扇入 | 扇出 | 活跃度 | 推荐策略 | 文件 | 行号 |"
        )
        lines.append(
            "|:------|:-------|:----:|:----:|:----:|:------:|:---------|:----|:----:|"
        )
        for sig in hardened_signals:
            activity = sig.fan_in + sig.fan_out
            rel_path = os.path.relpath(sig.file_path, scan_dir) if sig.file_path else ""
            lines.append(
                f"| - | {sig.name} | {sig.width} | {sig.fan_in} | "
                f"{sig.fan_out} | {activity} | {sig.strategy} | {rel_path} | {sig.line_no} |"
            )

    lines.append("")
    lines.append("## 统计摘要")
    lines.append(f"- 扫描信号总数: {total_signals}")
    lines.append(f"- 未加固候选: {len(candidates)}")
    lines.append(f"- 已加固信号: {len(hardened_signals)}")
    lines.append("")

    return "\n".join(lines)


# ============================================================
# 7. 自动检测项目根目录
# ============================================================

def auto_detect_project_root() -> Optional[str]:
    """
    自动检测项目根目录。

    搜索策略：
    1. 查找当前目录或上级目录中是否存在 Verilog 源文件目录（如 rtl/, src/, hdl/）
    2. 若当前目录包含 .v/.sv 文件，则返回当前目录
    3. 沿目录树向上搜索最多 3 层

    Returns:
        检测到的项目根目录路径，若未找到则返回 None
    """
    search_paths = [os.getcwd()]

    # 添加当前脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in search_paths:
        search_paths.append(script_dir)

    # 添加上级目录（最多 3 层）
    for base in list(search_paths):
        for _ in range(3):
            parent = os.path.dirname(base)
            if parent and parent != base and parent not in search_paths:
                search_paths.append(parent)
            base = parent

    # 常见 Verilog 源目录名
    rtl_dirs = {"rtl", "src", "hdl", "verilog", "design", "hardware"}

    for path in search_paths:
        # 检查是否有 rtl 等子目录
        for sub in rtl_dirs:
            candidate = os.path.join(path, sub)
            if os.path.isdir(candidate):
                return candidate
        # 检查路径中是否直接包含 .v 文件
        try:
            has_v_files = any(
                f.endswith(".v") for f in os.listdir(path)
            )
            if has_v_files:
                return path
        except PermissionError:
            continue

    # 兜底：返回当前工作目录（不再包含 ai_project 内部的回溯）
    return os.getcwd()


# ============================================================
# 8. 主流程
# ============================================================

def main():
    """主入口函数"""
    parser = argparse.ArgumentParser(
        description="扫描 Verilog/SystemVerilog 项目中的高扇出信号，生成加固建议报告"
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=3,
        help="扇入/扇出阈值，活跃度（扇入+扇出）超过此值的信号被列为候选（默认: 3）",
    )
    parser.add_argument(
        "--dir",
        type=str,
        default=None,
        help="扫描目录（默认: 自动检测项目根目录）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出文件路径（默认: 输出到 stdout）",
    )
    parser.add_argument(
        "--include-hardened",
        action="store_true",
        default=False,
        help="在候选列表中包含已加固的信号（默认: 仅显示未加固信号）",
    )

    args = parser.parse_args()

    # 确定扫描目录
    scan_dir = args.dir if args.dir else auto_detect_project_root()
    if not os.path.isdir(scan_dir):
        print(f"错误: 目录 '{scan_dir}' 不存在或无法访问。", file=sys.stderr)
        sys.exit(1)

    print(f"扫描目录: {scan_dir}", file=sys.stderr)

    # 查找 Verilog 文件
    verilog_files = find_verilog_files(scan_dir)
    if not verilog_files:
        print(f"警告: 在 '{scan_dir}' 中未找到 .v/.sv 文件。", file=sys.stderr)
        sys.exit(0)

    print(f"发现 {len(verilog_files)} 个 Verilog 文件", file=sys.stderr)

    # 解析所有信号
    all_signals: Dict[str, SignalInfo] = {}
    file_content_map: Dict[str, str] = {}

    for file_path in verilog_files:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except (IOError, OSError) as e:
            print(f"警告: 无法读取文件 '{file_path}': {e}", file=sys.stderr)
            continue

        file_content_map[file_path] = content

        # 解析信号声明
        file_signals = extract_declared_signals(content, file_path)

        # 扇入/扇出计数
        count_signal_activity(content, file_signals)

        # 合并到全局信号字典
        for sig_name, sig_info in file_signals.items():
            if sig_name in all_signals:
                # 合并扇入/扇出计数
                all_signals[sig_name].fan_in += sig_info.fan_in
                all_signals[sig_name].fan_out += sig_info.fan_out
                # 保留首次出现的文件/行号信息
            else:
                all_signals[sig_name] = sig_info

    total_signals = len(all_signals)
    print(f"解析到 {total_signals} 个信号", file=sys.stderr)

    # 检测加固状态
    check_hardening_status(all_signals, file_content_map)

    # 为未加固信号推荐策略
    for sig_name, sig_info in all_signals.items():
        if not sig_info.is_hardened:
            file_content = file_content_map.get(sig_info.file_path, "")
            sig_info.strategy = recommend_strategy(sig_info, file_content)

    # 按阈值筛选候选信号
    threshold = args.threshold
    candidates: List[SignalInfo] = []
    hardened_signals: List[SignalInfo] = []

    for sig_info in all_signals.values():
        activity = sig_info.fan_in + sig_info.fan_out
        if sig_info.is_hardened:
            hardened_signals.append(sig_info)
            if args.include_hardened and activity >= threshold:
                candidates.append(sig_info)
        elif activity >= threshold:
            candidates.append(sig_info)

    # 生成报告
    report = generate_report(
        candidates=candidates,
        hardened_signals=hardened_signals,
        scan_dir=scan_dir,
        threshold=threshold,
        total_signals=total_signals,
        scan_files=verilog_files,
    )

    # 输出
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(report)
            print(f"报告已保存至: {args.output}", file=sys.stderr)
        except (IOError, OSError) as e:
            print(f"错误: 无法写入文件 '{args.output}': {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(report)


if __name__ == "__main__":
    main()
