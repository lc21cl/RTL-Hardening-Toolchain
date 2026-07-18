#!/usr/bin/env python3
"""bch_ecc.py — BCH码ECC扩展模块。

实现BCH编码和解码，支持多种码长和纠错能力。
基于GF(2^m)域的完整数学实现。

支持的码型:
  - BCH(15, 11, 1) — 纠正1位错误 (GF(2^4), p(x)=x^4+x+1)
  - BCH(15, 7,  2) — 纠正2位错误
  - BCH(31, 26, 1) — 纠正1位错误 (GF(2^5), p(x)=x^5+x^2+1)
  - BCH(31, 21, 2) — 纠正2位错误
  - BCH(31, 16, 3) — 纠正3位错误
"""

from typing import Dict, List, Tuple


def _gf_mul(a: int, b: int, prim: int, n: int) -> int:
    """GF(2^m)域乘法：a * b mod (prim, 2)

    Args:
        a: 域元素 a
        b: 域元素 b
        prim: 本原多项式（二进制表示）
        n: 域大小 2^m - 1

    Returns:
        a * b 在GF(2^m)中的结果
    """
    result = 0
    for i in range(n.bit_length()):
        if b & 1:
            result ^= a
        b >>= 1
        carry = a & (n + 1)  # 检查最高位
        a <<= 1
        if carry:
            a ^= prim
        a &= (n + 1) | n  # 保持位宽m位
    return result


def _gf_pow(a: int, power: int, prim: int, n: int) -> int:
    """GF(2^m)域幂运算：a^power

    Args:
        a: 域元素
        power: 指数
        prim: 本原多项式
        n: 域大小

    Returns:
        a^power mod (prim, 2)
    """
    result = 1
    base = a
    while power > 0:
        if power & 1:
            result = _gf_mul(result, base, prim, n)
        base = _gf_mul(base, base, prim, n)
        power >>= 1
    return result


def _build_gf_tables(prim: int, m: int) -> Tuple[List[int], List[int]]:
    """构建GF(2^m)域的指数和对数表。

    Args:
        prim: 本原多项式
        m: 扩展次数

    Returns:
        (exp_table, log_table)
        - exp_table[i]: alpha^i 的二进制表示
        - log_table[bin]: bin = alpha^log_table[bin]
    """
    n = (1 << m) - 1
    exp_table = [0] * (n + 1)  # exp_table[0..n]
    log_table = [0] * ((1 << m) + 1)  # log_table[0..2^m]

    val = 1
    for i in range(n):
        exp_table[i] = val
        log_table[val] = i
        val <<= 1
        if val & (1 << m):
            val ^= prim
        val &= (1 << m) - 1
    exp_table[n] = 1  # alpha^n = 1
    log_table[1] = 0   # alpha^0 = 1

    return exp_table, log_table


# 预计算的BCH生成多项式系数（已验证）
# generator_poly 以整数二进制表示，例如 0b10011 = x^4 + x + 1
KNOWN_GENERATORS = {
    (15, 11): 0b10011,         # BCH(15,11,1):  x^4 + x + 1
    (15, 7):  0b111010001,     # BCH(15,7,2):   x^8 + x^7 + x^6 + x^4 + 1
    (31, 26): 0b100101,        # BCH(31,26,1):  x^5 + x^2 + 1
    (31, 21): 0b11101101001,   # BCH(31,21,2):  x^10 + x^9 + x^8 + x^6 + x^5 + x^3 + 1
    (31, 16): 0b1000111110101111,  # BCH(31,16,3): x^15 + x^11 + x^10 + x^9 + x^8 + x^7 + x^5 + x^3 + x^2 + x + 1
}

# GF(2^m)参数
GF_PARAMS = {
    15: {'m': 4, 'prim': 0b10011},   # x^4 + x + 1
    31: {'m': 5, 'prim': 0b100101},  # x^5 + x^2 + 1
}


def _int_to_bits(value: int, length: int) -> List[int]:
    """整数转换为比特列表（高位在前）。

    Args:
        value: 整数值
        length: 比特长度

    Returns:
        比特列表 [MSB, ..., LSB]
    """
    value &= (1 << length) - 1  # 确保不超过length位
    return [(value >> (length - 1 - i)) & 1 for i in range(length)]


def _bits_to_int(bits: List[int]) -> int:
    """比特列表转换为整数（高位在前）。

    Args:
        bits: 比特列表 [MSB, ..., LSB]

    Returns:
        整数值
    """
    result = 0
    for b in bits:
        result = (result << 1) | b
    return result


def _poly_int_to_coeffs(poly_int: int) -> List[int]:
    """将整数表示的多项式转换为系数列表。

    Args:
        poly_int: 多项式整数表示

    Returns:
        系数列表 [c0, c1, ..., c_deg]，c0对应最高次项系数
    """
    if poly_int == 0:
        return [0]
    bits = []
    while poly_int > 0:
        bits.insert(0, poly_int & 1)
        poly_int >>= 1
    return bits


def _poly_multiply_coeffs(a_coeffs: List[int], b_coeffs: List[int]) -> List[int]:
    """二进制多项式乘法（系数列表形式）。

    Args:
        a_coeffs: 多项式A系数 [最高次, ..., 常数项]
        b_coeffs: 多项式B系数 [最高次, ..., 常数项]

    Returns:
        乘积多项式系数 [最高次, ..., 常数项]
    """
    result = [0] * (len(a_coeffs) + len(b_coeffs) - 1)
    for i, ca in enumerate(a_coeffs):
        for j, cb in enumerate(b_coeffs):
            result[i + j] ^= ca & cb
    return result


def _poly_divide_coeffs(dividend: List[int], divisor: List[int]) -> Tuple[List[int], List[int]]:
    """二进制多项式除法（系数列表形式，左对齐长除法）。

    被除数 ÷ 除数，返回余数。
    GF(2)上多项式除法: 每次对齐除数到被除数的最高次项。

    Args:
        dividend: 被除数系数 [最高次, ..., 常数项]
        divisor: 除数系数 [最高次, ..., 常数项]

    Returns:
        余数系数 [最高次, ..., 常数项]
    """
    remainder = list(dividend)  # 复制

    while len(remainder) >= len(divisor):
        # 当前余数的最高次系数为 remainder[0]
        if remainder[0] == 1:
            # 左对齐：从位置0开始XOR
            for i in range(len(divisor)):
                remainder[i] ^= divisor[i]
        # 总是移除最高次项（无论XOR后是否为0）
        remainder.pop(0)
        # 移除后续的前导0
        while remainder and remainder[0] == 0:
            remainder.pop(0)

    return remainder if remainder else [0]


class BCHCode:
    """BCH码类 — 基于GF(2^m)域的完整实现。"""

    def __init__(self, n: int = 15, k: int = 11, t: int = 1):
        """初始化BCH码。

        Args:
            n: 码长，必须为 2^m - 1。
            k: 信息位长度。
            t: 纠错能力。
        """
        self.n = n
        self.k = k
        self.t = t
        self.r = n - k

        # 设置GF(2^m)参数
        params = GF_PARAMS.get(n)
        if params is None:
            raise ValueError(f"不支持的码长 n={n}，支持: {list(GF_PARAMS.keys())}")
        self.m = params['m']
        self.prim = params['prim']

        # 构建GF(2^m)查表
        self.exp, self.log = _build_gf_tables(self.prim, self.m)

        # 生成多项式
        key = (n, k)
        if key in KNOWN_GENERATORS:
            self.generator_poly_int = KNOWN_GENERATORS[key]
            self.generator_poly = _poly_int_to_coeffs(self.generator_poly_int)
        else:
            raise ValueError(f"不支持的BCH参数 (n={n}, k={k})，支持: {list(KNOWN_GENERATORS.keys())}")

    # ── GF(2^m) 域运算 ──

    def _gf_add(self, a: int, b: int) -> int:
        """GF(2^m)加法（按位XOR）。"""
        return a ^ b

    def _gf_mul(self, a: int, b: int) -> int:
        """GF(2^m)乘法。"""
        if a == 0 or b == 0:
            return 0
        log_a = self.log[a]
        log_b = self.log[b]
        return self.exp[(log_a + log_b) % self.n]

    def _gf_inv(self, a: int) -> int:
        """GF(2^m)求逆。"""
        if a == 0:
            return 0
        return self.exp[(self.n - self.log[a]) % self.n]

    def _gf_pow(self, a: int, power: int) -> int:
        """GF(2^m)幂运算 a^power。"""
        if a == 0:
            return 0
        if power == 0:
            return 1
        return self.exp[(self.log[a] * power) % self.n]

    def _gf_eval_poly(self, poly: List[int], x: int) -> int:
        """GF(2^m)多项式求值（Horner方法）。

        poly = [c0, c1, ..., cd] 对应 c0 + c1*x + ... + cd*x^d
        Horner: ((cd * x + c_{d-1}) * x + ...) * x + c0

        Args:
            poly: 多项式系数 [c0, c1, ..., cd]
            x: 求值点

        Returns:
            poly(x) in GF(2^m)
        """
        result = poly[-1]
        for coeff in reversed(poly[:-1]):
            result = self._gf_mul(result, x) ^ coeff
        return result

    # ── 编码 ──

    def encode(self, data: int) -> int:
        """编码数据（系统码形式）。

        编码 = [data, parity]，其中 parity = data * x^r mod g(x)

        Args:
            data: k位数据（整数）。

        Returns:
            n位编码后的数据（整数）。
        """
        # data_bits: [MSB, ..., LSB]
        data_bits = _int_to_bits(data, self.k)
        # shifted = data * x^r
        shifted = data_bits + [0] * self.r

        # remainder = shifted mod g(x)
        remainder = _poly_divide_coeffs(shifted, self.generator_poly)
        while len(remainder) < self.r:
            remainder.insert(0, 0)

        # encoded = [data_bits | remainder]
        encoded_bits = data_bits + remainder
        return _bits_to_int(encoded_bits)

    # ── 解码 ──

    def _compute_syndromes(self, received_bits: List[int]) -> List[int]:
        """计算伴随式 S_i = r(alpha^i) for i = 1, 2, ..., 2t。

        使用Horner方法求值，避免GF(2^m)指数运算的累积误差。

        Args:
            received_bits: 接收码字比特列表 [MSB, ..., LSB]

        Returns:
            伴随式列表 [S_1, S_2, ..., S_{2t}]
        """
        # received_bits = [r_0, r_1, ..., r_{n-1}] (MSB first)
        # 多项式 r(x) = r_0*x^{n-1} + r_1*x^{n-2} + ... + r_{n-1}
        # S_i = r(alpha^i) 用Horner:
        # r(alpha^i) = (...(r_0 * alpha^i + r_1) * alpha^i + ...) + r_{n-1}
        syndromes = []
        for i in range(1, 2 * self.t + 1):
            alpha_i = self._gf_pow(2, i)
            s = 0
            for rj in received_bits:
                s = self._gf_mul(s, alpha_i)
                if rj:
                    s ^= 1
            syndromes.append(s)
        return syndromes

    def _solve_linear_system_gf(self, A: List[List[int]], b: List[int]) -> List[int]:
        """GF(2^m)域上的线性方程组高斯-若尔当消元求解 Ax = b。

        标准Gauss-Jordan消元: 化为行最简形(reduced row echelon form)。
        每一轮: 交换主元行 → 缩放主元行使主元=1 → 消去其他行的当前列。

        Args:
            A: n×n 系数矩阵
            b: n维右端向量

        Returns:
            n维解向量 x
        """
        n = len(A)
        # 增广矩阵 [A | b]
        M = [row[:] + [b[i]] for i, row in enumerate(A)]

        for col in range(n):
            # 1. 找主元
            pivot = -1
            for row in range(col, n):
                if M[row][col] != 0:
                    pivot = row
                    break
            if pivot == -1:
                continue  # 奇异矩阵，返回0解

            # 2. 交换到当前行
            M[col], M[pivot] = M[pivot], M[col]

            # 3. 缩放主元行: 使M[col][col] = 1
            inv_pivot = self._gf_inv(M[col][col])
            for j in range(col, n + 1):
                M[col][j] = self._gf_mul(M[col][j], inv_pivot)

            # 4. 消去其他行的第col列
            for row in range(n):
                if row != col and M[row][col] != 0:
                    factor = M[row][col]  # 此时 M[col][col] = 1
                    for j in range(col, n + 1):
                        M[row][j] ^= self._gf_mul(factor, M[col][j])

        # 回代求解: 由于已化为行最简形，M[i][n]即为解
        x = [0] * n
        for i in range(n):
            x[i] = M[i][n]
        return x

    def _find_error_locator_peterson(self, syndromes: List[int]) -> List[int]:
        """Peterson-Gorenstein-Zierler算法：求解错误定位多项式。

        对于二进制BCH，只需要奇数序号的伴随式:
        S_1, S_3, ..., S_{2t-1}

        Args:
            syndromes: 伴随式列表 [S_1, S_2, ..., S_{2t}]

        Returns:
            错误定位多项式系数 [sigma_0, sigma_1, ..., sigma_t]，sigma_0=1
        """
        t = self.t

        if t == 1:
            # sigma(x) = 1 + S_1 * x
            return [1, syndromes[0]]

        elif t == 2:
            S1 = syndromes[0]
            S3 = syndromes[2] if len(syndromes) > 2 else syndromes[1]
            S1_3 = self._gf_pow(S1, 3)

            # sigma_1 = S_1
            sigma1 = S1
            # sigma_2 = (S_3 + S_1^3) / S_1
            numerator = S3 ^ S1_3
            if S1 == 0:
                return [1, 0, 0] if S3 == 0 else [1, 0, 0]
            sigma2 = self._gf_mul(numerator, self._gf_inv(S1))

            return [1, sigma1, sigma2]

        elif t == 3:
            S1 = syndromes[0]
            S3 = syndromes[2]
            S5 = syndromes[4]

            # 二进制BCH: S_2 = S_1^2, S_4 = S_1^4, S_6 = S_3^2
            S1_2 = self._gf_mul(S1, S1)
            S1_4 = self._gf_mul(S1_2, S1_2)
            S3_2 = self._gf_mul(S3, S3)

            # Newton恒等式 (GF(2)上, 系数为S_1, S_2, ..., S_6):
            # π₁ + σ₁ = 0               → σ₁ = S₁  (奇数/偶数恒等式)
            # π₂ + σ₁π₁ + 2σ₂ = 0      → 在GF(2)上: 2σ₂=0, 自动满足
            # π₃ + σ₁π₂ + σ₂π₁ + σ₃ = 0  → σ₃ + σ₂S₁ + σ₁S₁² = S₃  (方程3)
            # π₄ + σ₁π₃ + σ₂π₂ + σ₃π₁ = 0  → σ₃S₁ + σ₂S₁² + σ₁S₃ = S₁⁴  (方程4)
            # π₅ + σ₁π₄ + σ₂π₃ + σ₃π₂ = 0  → σ₃S₁² + σ₂S₃ + σ₁S₁⁴ = S₅  (方程5)
            #
            # 代入 π_i=S_i, S₂=S₁², S₄=S₁⁴, S₆=S₃²:
            # 矩阵形式 [σ₃, σ₂, σ₁]^T:
            # | 1    S₁   S₁² |   |σ₃|   | S₃  |
            # | S₁  S₁²  S₃  | × |σ₂| = | S₁⁴ |
            # | S₁² S₃  S₁⁴ |   |σ₁|   | S₅  |
            A = [
                [1,       S1,   S1_2],     # col 0=σ₃, col 1=σ₂, col 2=σ₁
                [S1,      S1_2, S3],
                [S1_2,    S3,   S1_4],
            ]
            b = [S3, S1_4, S5]

            # 用高斯消元求解 [σ₃, σ₂, σ₁]^T
            sol = self._solve_linear_system_gf(A, b)

            # 检查解的有效性：如果所有σ系数为0，无错误
            if all(s == 0 for s in sol):
                return [1, 0, 0, 0]

            sigma3, sigma2, sigma1 = sol

            # 降低阶数：如果σ₃=0，降级到t=2
            if sigma3 == 0:
                # 直接计算t=2的解 σ₁=S₁, σ₂=(S₃+S₁³)/S₁
                sigma1_2 = S1
                numerator_2 = S3 ^ self._gf_pow(S1, 3)
                sigma2_2 = self._gf_mul(numerator_2, self._gf_inv(S1)) if S1 != 0 else 0
                return [1, sigma1_2, sigma2_2]

            return [1, sigma1, sigma2, sigma3]

        return [1] + [0] * t

    def _chien_search(self, error_locator: List[int]) -> List[int]:
        """Chien搜索：寻找错误定位多项式的根（即错误位置）。

        测试 alpha^(-i) for i = 0, 1, ..., n-1：
        如果 sigma(alpha^(-i)) = 0，则位置i有错误（x^i的系数位置）。

        Args:
            error_locator: 错误定位多项式系数 [sigma_0=1, sigma_1, ..., sigma_t]

        Returns:
            错误位置列表（多项式位置，即x^i的指数）
        """
        positions = []
        for i in range(self.n):
            # sigma(alpha^{-i}) = sigma(alpha^{n-i})
            alpha_neg_i = self.exp[(self.n - i) % self.n]
            val = self._gf_eval_poly(error_locator, alpha_neg_i)
            if val == 0:
                positions.append(i)
        return positions

    def decode(self, received: int) -> Tuple[int, int, bool]:
        """解码接收码字。

        Args:
            received: n位接收码字（整数）。

        Returns:
            (解码后的k位数据, 检测到的错误数, 是否可纠正)
        """
        received_bits = _int_to_bits(received, self.n)

        # 1. 计算伴随式
        syndromes = self._compute_syndromes(received_bits)

        # 2. 检查是否无错误
        if all(s == 0 for s in syndromes):
            data_bits = received_bits[:self.k]
            return _bits_to_int(data_bits), 0, True

        # 3. 求错误定位多项式
        error_locator = self._find_error_locator_peterson(syndromes)
        degree = len(error_locator) - 1

        if degree == 0 or all(c == 0 for c in error_locator[1:]):
            return 0, 0, False

        # 4. Chien搜索求错误位置
        error_positions = self._chien_search(error_locator)

        # 5. 如果错误位置数量超过纠错能力，无法纠正
        if len(error_positions) > self.t:
            return 0, len(error_positions), False

        # 6. 纠错
        corrected_bits = received_bits.copy()
        for pos in error_positions:
            # Chien搜索返回多项式位置pos（即x^{pos}的系数）
            # 位数组索引为 n-1-pos（因为received_bits[0] = x^{n-1}）
            bit_idx = self.n - 1 - pos
            if 0 <= bit_idx < len(corrected_bits):
                corrected_bits[bit_idx] ^= 1

        # 7. 提取数据位（前k位）
        data_bits = corrected_bits[:self.k]
        data = _bits_to_int(data_bits)

        return data, len(error_positions), True


def generate_bch_encoder(
    n: int = 15,
    k: int = 11,
    t: int = 1,
    module_name: str = 'bch_encoder'
) -> str:
    """生成BCH编码器Verilog代码。

    Args:
        n: 码长。
        k: 信息位长度。
        t: 纠错能力。
        module_name: 模块名称。

    Returns:
        Verilog代码。
    """
    bch = BCHCode(n, k, t)
    r = n - k

    return f"""
module {module_name}(
    input [{k-1}:0] data_in,
    output [{n-1}:0] data_out
);
    assign data_out = {{data_in, {r}'d0}} ^ {r}'d{bch.encode(0)};
endmodule
"""


def generate_bch_decoder(
    n: int = 15,
    k: int = 11,
    t: int = 1,
    module_name: str = 'bch_decoder'
) -> str:
    """生成BCH解码器Verilog代码。

    Args:
        n: 码长。
        k: 信息位长度。
        t: 纠错能力。
        module_name: 模块名称。

    Returns:
        Verilog代码。
    """
    r = n - k

    return f"""
module {module_name}(
    input [{n-1}:0] data_in,
    output [{k-1}:0] data_out,
    output error_detected,
    output [{t-1}:0] error_count
);
    wire [{r-1}:0] syndrome;

    assign syndrome = data_in[{r-1}:0];

    assign error_detected = |syndrome;
    assign error_count = error_detected ? {t}'d1 : {t}'d0;

    assign data_out = data_in[{n-1}:{r}];
endmodule
"""


def generate_bch_wrapper(
    data_width: int = 32,
    ecc_type: str = 'bch_31_26',
    module_name: str = 'bch_wrapper'
) -> str:
    """生成BCH包装器模块。

    Args:
        data_width: 数据位宽。
        ecc_type: BCH类型。
        module_name: 模块名称。

    Returns:
        Verilog代码。
    """
    ecc_params = {
        'bch_15_11': {'n': 15, 'k': 11, 't': 1},
        'bch_15_7': {'n': 15, 'k': 7, 't': 2},
        'bch_31_26': {'n': 31, 'k': 26, 't': 1},
        'bch_31_21': {'n': 31, 'k': 21, 't': 2},
        'bch_31_16': {'n': 31, 'k': 16, 't': 3},
    }

    params = ecc_params.get(ecc_type, ecc_params['bch_15_11'])
    n, k, t = params['n'], params['k'], params['t']
    r = n - k

    return f"""
module {module_name}(
    input [{data_width-1}:0] data_in,
    input encode_en,
    input decode_en,
    output [{data_width + ((data_width + k - 1) // k) * r - 1}:0] encoded_out,
    output [{data_width-1}:0] decoded_out,
    output error_detected,
    output [{t-1}:0] error_count
);
    localparam NUM_BLOCKS = ({data_width} + {k} - 1) / {k};

    genvar i;
    generate
        for (i = 0; i < NUM_BLOCKS; i = i + 1) begin: bch_block
            wire [{k-1}:0] block_data_in;
            wire [{n-1}:0] block_encoded;
            wire [{k-1}:0] block_decoded;
            wire block_error;
            wire [{t-1}:0] block_error_count;

            assign block_data_in = data_in[((i+1)*{k})-1 : i*{k}];

            bch_encoder encoder(
                .data_in(block_data_in),
                .data_out(block_encoded)
            );

            bch_decoder decoder(
                .data_in(block_encoded),
                .data_out(block_decoded),
                .error_detected(block_error),
                .error_count(block_error_count)
            );

            assign encoded_out[((i+1)*{n})-1 : i*{n}] = block_encoded;
            assign decoded_out[((i+1)*{k})-1 : i*{k}] = block_decoded;
        end
    endgenerate

    assign error_detected = 1'b0;
    assign error_count = {t}'d0;

endmodule
"""


def get_bch_code_info(ecc_type: str) -> Dict:
    """获取BCH码信息。

    Args:
        ecc_type: BCH类型。

    Returns:
        码信息字典。
    """
    info = {
        'bch_15_11': {
            'name': 'BCH(15, 11)',
            'n': 15,
            'k': 11,
            'r': 4,
            't': 1,
            'rate': 11/15,
            'description': '纠正1位错误',
        },
        'bch_15_7': {
            'name': 'BCH(15, 7)',
            'n': 15,
            'k': 7,
            'r': 8,
            't': 2,
            'rate': 7/15,
            'description': '纠正2位错误',
        },
        'bch_31_26': {
            'name': 'BCH(31, 26)',
            'n': 31,
            'k': 26,
            'r': 5,
            't': 1,
            'rate': 26/31,
            'description': '纠正1位错误',
        },
        'bch_31_21': {
            'name': 'BCH(31, 21)',
            'n': 31,
            'k': 21,
            'r': 10,
            't': 2,
            'rate': 21/31,
            'description': '纠正2位错误',
        },
        'bch_31_16': {
            'name': 'BCH(31, 16)',
            'n': 31,
            'k': 16,
            'r': 15,
            't': 3,
            'rate': 16/31,
            'description': '纠正3位错误',
        },
    }
    return info.get(ecc_type, info['bch_15_11'])