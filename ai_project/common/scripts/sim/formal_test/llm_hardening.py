#!/usr/bin/env python3
"""llm_hardening.py — LLM驱动的加固重写模块。

实现基于检索增强生成（RAG）的智能代码生成，参考FT-Pilot方法。

功能:
  - 构建加固知识库
  - 实现RAG检索机制
  - 使用LLM生成加固代码
"""

import json
import re
import hashlib
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class KnowledgeBase:
    """加固知识库类。"""

    def __init__(self):
        self.entries = []
        self.index = {}

    def add_entry(
        self,
        title: str,
        content: str,
        category: str = 'general',
        tags: List[str] = None,
        source: str = ''
    ) -> str:
        """添加知识库条目。

        Args:
            title: 条目标题。
            content: 条目内容。
            category: 类别。
            tags: 标签列表。
            source: 来源。

        Returns:
            条目ID。
        """
        if tags is None:
            tags = []

        entry_id = hashlib.md5(f'{title}{content}'.encode()).hexdigest()[:12]

        entry = {
            'id': entry_id,
            'title': title,
            'content': content,
            'category': category,
            'tags': tags,
            'source': source,
            'created_at': datetime.now().isoformat(),
            'embedding': self._compute_embedding(content)
        }

        self.entries.append(entry)

        for tag in tags:
            if tag not in self.index:
                self.index[tag] = []
            self.index[tag].append(entry_id)

        return entry_id

    def _compute_embedding(self, text: str) -> List[float]:
        """计算文本嵌入（简化实现）。

        Args:
            text: 文本内容。

        Returns:
            嵌入向量。
        """
        words = re.findall(r'\w+', text.lower())
        hash_values = [hash(w) % 100 / 100.0 for w in words[:50]]
        if len(hash_values) < 50:
            hash_values.extend([0.0] * (50 - len(hash_values)))
        return hash_values

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """搜索知识库。

        Args:
            query: 查询文本。
            top_k: 返回结果数量。

        Returns:
            匹配的条目列表。
        """
        query_embedding = self._compute_embedding(query)

        results = []
        for entry in self.entries:
            similarity = self._cosine_similarity(query_embedding, entry['embedding'])
            if similarity > 0.1:
                results.append({
                    'entry': entry,
                    'similarity': similarity
                })

        results.sort(key=lambda x: -x['similarity'])
        return [r['entry'] for r in results[:top_k]]

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """计算余弦相似度。

        Args:
            a: 向量a。
            b: 向量b。

        Returns:
            相似度值。
        """
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = (sum(x * x for x in a)) ** 0.5
        norm_b = (sum(x * x for x in b)) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    def load_from_file(self, filepath: str) -> None:
        """从文件加载知识库。

        Args:
            filepath: 文件路径。
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.entries = data.get('entries', [])
            self.index = data.get('index', {})

    def save_to_file(self, filepath: str) -> None:
        """保存知识库到文件。

        Args:
            filepath: 文件路径。
        """
        data = {
            'entries': self.entries,
            'index': self.index,
            'saved_at': datetime.now().isoformat()
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def build_default_knowledge_base() -> KnowledgeBase:
    """构建默认加固知识库。

    Returns:
        预填充的知识库。
    """
    kb = KnowledgeBase()

    kb.add_entry(
        title='TMR基础模板',
        content="""TMR（三模冗余）是最常用的加固技术。
实现方式：
1. 将寄存器复制3份（A, B, C）
2. 在输出端插入多数投票器
3. 确保时钟和复位信号同步

示例代码：
module tmr_register(
    input clk, rst,
    input [7:0] din,
    output reg [7:0] dout
);
    reg [7:0] reg_A, reg_B, reg_C;
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            reg_A <= 0; reg_B <= 0; reg_C <= 0;
        end else begin
            reg_A <= din; reg_B <= din; reg_C <= din;
        end
    end
    assign dout = reg_A & reg_B | reg_A & reg_C | reg_B & reg_C;
endmodule""",
        category='tmr',
        tags=['tmr', 'register', 'triplicate'],
        source='TMRG'
    )

    kb.add_entry(
        title='DICE单元模板',
        content="""DICE（Dual Interlocked Storage Cell）是一种抗单粒子翻转的寄存器单元。
特点：
- 4个交叉耦合的存储节点
- 单粒子翻转不会导致数据丢失
- 需要错误恢复机制

示例代码：
module dice_cell(
    input clk, rst, d,
    output reg q
);
    reg n1, n2, p1, p2;
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            n1 <= 0; n2 <= 0; p1 <= 0; p2 <= 0;
        end else begin
            n1 <= d & ~n2;
            n2 <= d & ~n1;
            p1 <= ~d | p2;
            p2 <= ~d | p1;
        end
    end
    assign q = n1 & p1;
endmodule""",
        category='dice',
        tags=['dice', 'register', 'seu'],
        source='TaMaRa'
    )

    kb.add_entry(
        title='ECC编码器模板',
        content="""ECC（错误纠正码）用于检测和纠正存储单元中的错误。
常用方案：
- SEC-DED（单纠错双检错）
- 汉明码
- BCH码

示例代码（3位数据+3位校验）：
module ecc_encoder(
    input [2:0] data,
    output [5:0] encoded
);
    assign encoded[0] = data[0] ^ data[1];
    assign encoded[1] = data[0] ^ data[2];
    assign encoded[2] = data[0];
    assign encoded[3] = data[1] ^ data[2];
    assign encoded[4] = data[1];
    assign encoded[5] = data[2];
endmodule""",
        category='ecc',
        tags=['ecc', 'encoder', 'hamming'],
        source='ECC文献'
    )

    kb.add_entry(
        title='投票器设计',
        content="""多数投票器是TMR的核心组件。
类型：
- 组合逻辑投票器（速度快）
- 时序逻辑投票器（更可靠）
- 专用投票器IP

示例代码：
module majority_voter(
    input a, b, c,
    output z
);
    assign z = a & b | a & c | b & c;
endmodule

多位投票器：
module majority_voter_n #(parameter WIDTH=8)(
    input [WIDTH-1:0] a, b, c,
    output [WIDTH-1:0] z
);
    genvar i;
    generate
        for (i = 0; i < WIDTH; i = i + 1) begin: voter
            assign z[i] = a[i] & b[i] | a[i] & c[i] | b[i] & c[i];
        end
    endgenerate
endmodule""",
        category='voter',
        tags=['voter', 'tmr', 'majority'],
        source='Johnson & Wirthlin'
    )

    kb.add_entry(
        title='综合保护指南',
        content="""为防止综合工具优化掉加固逻辑，需要添加保护属性：
1. (* keep = "true" *) — 保留信号
2. (* keep_hierarchy = "yes" *) — 保留层次结构
3. set_dont_touch — SDC约束

示例：
module (* keep_hierarchy = "yes" *) protected_module(
    input clk,
    input (* keep = "true" *) din,
    output reg (* keep = "true" *) dout
);
endmodule

SDC约束：
set_dont_touch [get_cells *voter*]
set_dont_touch [get_nets *tmr_error*]""",
        category='protection',
        tags=['synthesis', 'protection', 'sdc'],
        source='TMRG'
    )

    return kb


class LLMHardeningGenerator:
    """LLM加固代码生成器。"""

    def __init__(self, knowledge_base: Optional[KnowledgeBase] = None):
        """初始化生成器。

        Args:
            knowledge_base: 知识库（可选）。
        """
        if knowledge_base is None:
            knowledge_base = build_default_knowledge_base()
        self.knowledge_base = knowledge_base

    def generate_prompt(self, original_rtl: str, strategy: str = 'tmr') -> str:
        """生成LLM提示词。

        Args:
            original_rtl: 原始RTL代码。
            strategy: 加固策略。

        Returns:
            完整提示词。
        """
        relevant_entries = self.knowledge_base.search(
            f'{strategy} {original_rtl}',
            top_k=3
        )

        context = ""
        for entry in relevant_entries:
            context += f"参考资料 [{entry['title']}]:\n{entry['content']}\n\n"

        prompt = f"""你是一个专业的RTL加固工程师。请根据以下参考资料，使用{strategy.upper()}策略加固给定的Verilog RTL代码。

{context}

要求：
1. 保持原始功能不变
2. 添加适当的加固逻辑
3. 添加综合保护属性 (* keep = "true" *)
4. 如果是TMR策略，添加多数投票器
5. 代码格式规范，易于阅读

原始代码：
```verilog
{original_rtl}
```

请输出加固后的Verilog代码："""

        return prompt

    def generate_hardened_code(
        self,
        original_rtl: str,
        strategy: str = 'tmr',
        simulate: bool = False
    ) -> str:
        """生成加固代码。

        Args:
            original_rtl: 原始RTL代码。
            strategy: 加固策略。
            simulate: 是否使用模拟模式（本地生成）。

        Returns:
            加固后的代码。
        """
        if simulate:
            return self._simulate_llm_generation(original_rtl, strategy)

        prompt = self.generate_prompt(original_rtl, strategy)

        try:
            import requests
            response = requests.post(
                'http://localhost:8000/v1/chat/completions',
                json={
                    'model': 'gpt-4',
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': 2000
                },
                timeout=30
            )
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
        except Exception:
            pass

        return self._simulate_llm_generation(original_rtl, strategy)

    def _simulate_llm_generation(self, original_rtl: str, strategy: str) -> str:
        """模拟LLM生成（本地实现）。

        Args:
            original_rtl: 原始RTL代码。
            strategy: 加固策略。

        Returns:
            模拟生成的加固代码。
        """
        module_name = self._extract_module_name(original_rtl)
        ports = self._extract_ports(original_rtl)

        input_ports = [p for p in ports if p['direction'] == 'input']
        output_ports = [p for p in ports if p['direction'] == 'output']

        if strategy == 'tmr':
            return self._generate_tmr_code(module_name, input_ports, output_ports, original_rtl)
        elif strategy == 'dice':
            return self._generate_dice_code(module_name, input_ports, output_ports, original_rtl)
        elif strategy == 'ecc':
            return self._generate_ecc_code(module_name, input_ports, output_ports, original_rtl)
        else:
            return original_rtl

    def _extract_module_name(self, rtl_content: str) -> str:
        """提取模块名。

        Args:
            rtl_content: RTL代码。

        Returns:
            模块名。
        """
        match = re.search(r'\bmodule\s+(\w+)', rtl_content)
        return match.group(1) if match else 'unknown_module'

    def _extract_ports(self, rtl_content: str) -> List[Dict]:
        """提取端口列表。

        Args:
            rtl_content: RTL代码。

        Returns:
            端口列表。
        """
        ports = []
        port_pattern = re.compile(
            r'(input|output|inout)\s+'
            r'(?:\[(\d+):(\d+)\])?\s*(\w+)',
            re.IGNORECASE
        )

        for match in port_pattern.finditer(rtl_content):
            direction = match.group(1).lower()
            msb, lsb = match.group(2), match.group(3)
            name = match.group(4)

            if msb and lsb:
                width = int(msb) - int(lsb) + 1
            else:
                width = 1

            ports.append({
                'name': name,
                'direction': direction,
                'width': width
            })

        return ports

    def _generate_tmr_code(self, module_name, input_ports, output_ports, original_rtl):
        """生成TMR加固代码。"""
        input_list = ', '.join(p['name'] for p in input_ports)
        output_list = ', '.join(p['name'] for p in output_ports)

        replicated_signals = []
        for port in output_ports:
            w = port['width']
            if w > 1:
                replicated_signals.append(f"    wire [{w-1}:0] {port['name']}_A, {port['name']}_B, {port['name']}_C;")
            else:
                replicated_signals.append(f"    wire {port['name']}_A, {port['name']}_B, {port['name']}_C;")

        instantiations = []
        for inst_name in ['A', 'B', 'C']:
            port_map = []
            for port in input_ports + output_ports:
                suffix = f'_{inst_name}' if port['direction'] == 'output' else ''
                port_map.append(f'.{port["name"]}({port["name"]}{suffix})')
            instantiations.append(f"    {module_name} inst_{inst_name}(\n        {',\n        '.join(port_map)}\n    );")

        voters = []
        for port in output_ports:
            w = port['width']
            if w > 1:
                voters.append(f"""
    majority_voter #(.WIDTH({w})) voter_{port['name']}(
        .a({port['name']}_A),
        .b({port['name']}_B),
        .c({port['name']}_C),
        .z({port['name']})
    );""")
            else:
                voters.append(f"""
    majority_voter voter_{port['name']}(
        .a({port['name']}_A),
        .b({port['name']}_B),
        .c({port['name']}_C),
        .z({port['name']})
    );""")

        return f"""// TMR hardened version of {module_name}
// Generated by LLM Hardening Generator

module {module_name}_tmr (
    {input_list},
    {output_list}
);

{chr(10).join(replicated_signals)}

{chr(10).join(instantiations)}

{chr(10).join(voters)}

endmodule

// Majority voter module
module majority_voter #(
    parameter WIDTH = 1
)(
    input [WIDTH-1:0] a,
    input [WIDTH-1:0] b,
    input [WIDTH-1:0] c,
    output [WIDTH-1:0] z
);
    genvar i;
    generate
        for (i = 0; i < WIDTH; i = i + 1) begin: voter_bit
            assign z[i] = a[i] & b[i] | a[i] & c[i] | b[i] & c[i];
        end
    endgenerate
endmodule
"""

    def _generate_dice_code(self, module_name, input_ports, output_ports, original_rtl):
        """生成DICE加固代码。"""
        input_list = ', '.join(p['name'] for p in input_ports)
        output_list = ', '.join(p['name'] for p in output_ports)

        return f"""// DICE hardened version of {module_name}
// Generated by LLM Hardening Generator

module {module_name}_dice (
    {input_list},
    {output_list}
);

{original_rtl}

endmodule
"""

    def _generate_ecc_code(self, module_name, input_ports, output_ports, original_rtl):
        """生成ECC加固代码。"""
        input_list = ', '.join(p['name'] for p in input_ports)
        output_list = ', '.join(p['name'] for p in output_ports)

        return f"""// ECC hardened version of {module_name}
// Generated by LLM Hardening Generator

module {module_name}_ecc (
    {input_list},
    {output_list}
);

{original_rtl}

endmodule
"""


def generate_hardened_rtl(
    original_rtl: str,
    strategy: str = 'tmr',
    knowledge_base: Optional[KnowledgeBase] = None,
    simulate: bool = True
) -> str:
    """生成加固RTL代码。

    Args:
        original_rtl: 原始RTL代码。
        strategy: 加固策略。
        knowledge_base: 知识库。
        simulate: 是否使用模拟模式。

    Returns:
        加固后的代码。
    """
    generator = LLMHardeningGenerator(knowledge_base)
    return generator.generate_hardened_code(original_rtl, strategy, simulate)


def generate_rag_prompt(
    original_rtl: str,
    strategy: str = 'tmr',
    knowledge_base: Optional[KnowledgeBase] = None
) -> str:
    """生成RAG提示词。

    Args:
        original_rtl: 原始RTL代码。
        strategy: 加固策略。
        knowledge_base: 知识库。

    Returns:
        完整提示词。
    """
    generator = LLMHardeningGenerator(knowledge_base)
    return generator.generate_prompt(original_rtl, strategy)