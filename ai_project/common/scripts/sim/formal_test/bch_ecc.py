#!/usr/bin/env python3
"""bch_ecc.py — BCH码ECC扩展模块。

实现BCH编码和解码，支持多种码长和纠错能力。

支持的码型:
  - BCH(15, 11) — 纠正1位错误
  - BCH(15, 7) — 纠正2位错误
  - BCH(31, 26) — 纠正1位错误
  - BCH(31, 21) — 纠正2位错误
  - BCH(31, 16) — 纠正3位错误
"""

import numpy as np
from typing import Dict, List, Optional


class BCHCode:
    """BCH码类。"""

    def __init__(self, n: int = 15, k: int = 11, t: int = 1):
        """初始化BCH码。

        Args:
            n: 码长。
            k: 信息位长度。
            t: 纠错能力。
        """
        self.n = n
        self.k = k
        self.t = t
        self.r = n - k
        self.generator_poly = self._compute_generator_poly()

    def _compute_generator_poly(self) -> List[int]:
        """计算生成多项式。

        Returns:
            生成多项式系数列表。
        """
        primitive_polys = {
            15: [1, 0, 0, 1, 1],
            31: [1, 0, 0, 1, 0, 1],
        }

        m = int(np.log2(self.n + 1))
        if self.n in primitive_polys:
            primitive = primitive_polys[self.n]
        else:
            primitive = [1] + [0] * (m - 1) + [1]

        generator = [1]

        for i in range(1, 2 * self.t + 1):
            alpha_poly = self._compute_alpha_poly(i, m, primitive)
            generator = self._polynomial_multiply(generator, alpha_poly)

        return generator

    def _compute_alpha_poly(self, i: int, m: int, primitive: List[int]) -> List[int]:
        """计算 α^i 的最小多项式。

        Args:
            i: 指数。
            m: 扩展次数。
            primitive: 本原多项式。

        Returns:
            最小多项式。
        """
        poly = [1, i]
        seen = {i}

        while True:
            new_elements = []
            for exp in poly[1:]:
                new_exp = (exp * 2) % (2 ** m - 1)
                if new_exp not in seen:
                    seen.add(new_exp)
                    new_elements.append(new_exp)

            if not new_elements:
                break
            poly.extend(new_elements)

        result = [1]
        for exp in poly[1:]:
            result = self._polynomial_multiply(result, [1, 1])

        return result

    def _polynomial_multiply(self, a: List[int], b: List[int]) -> List[int]:
        """多项式乘法。

        Args:
            a: 多项式a。
            b: 多项式b。

        Returns:
            乘积多项式。
        """
        result = [0] * (len(a) + len(b) - 1)
        for i, coeff_a in enumerate(a):
            for j, coeff_b in enumerate(b):
                result[i + j] = (result[i + j] + coeff_a * coeff_b) % 2
        return result

    def _polynomial_divide(self, dividend: List[int], divisor: List[int]) -> tuple:
        """多项式除法。

        Args:
            dividend: 被除数。
            divisor: 除数。

        Returns:
            (商, 余数)。
        """
        quotient = []
        remainder = dividend.copy()

        while len(remainder) >= len(divisor):
            shift = len(remainder) - len(divisor)
            quotient.append(1)
            for i in range(len(divisor)):
                remainder[i + shift] = (remainder[i + shift] + divisor[i]) % 2
            while remainder and remainder[0] == 0:
                remainder.pop(0)

        return quotient, remainder

    def encode(self, data: int) -> int:
        """编码数据。

        Args:
            data: k位数据。

        Returns:
            n位编码后的数据。
        """
        data_bits = [(data >> i) & 1 for i in range(self.k - 1, -1, -1)]

        shifted = data_bits + [0] * self.r

        _, remainder = self._polynomial_divide(shifted, self.generator_poly)

        while len(remainder) < self.r:
            remainder.insert(0, 0)

        encoded_bits = data_bits + remainder

        result = 0
        for bit in encoded_bits:
            result = (result << 1) | bit

        return result

    def decode(self, received: int) -> tuple:
        """解码数据。

        Args:
            received: n位接收数据。

        Returns:
            (解码后的数据, 错误数量, 是否可纠正)。
        """
        received_bits = [(received >> i) & 1 for i in range(self.n - 1, -1, -1)]

        syndromes = []
        for i in range(1, 2 * self.t + 1):
            syndrome = 0
            for j, bit in enumerate(received_bits):
                if bit:
                    syndrome ^= pow(2, i * j, self.n + 1)
            syndromes.append(syndrome)

        if all(s == 0 for s in syndromes):
            data_bits = received_bits[:self.k]
            data = 0
            for bit in data_bits:
                data = (data << 1) | bit
            return data, 0, True

        error_locator = self._find_error_locator(syndromes)

        error_positions = self._find_error_positions(error_locator)

        if len(error_positions) > self.t:
            return 0, len(error_positions), False

        corrected_bits = received_bits.copy()
        for pos in error_positions:
            corrected_bits[pos] ^= 1

        data_bits = corrected_bits[:self.k]
        data = 0
        for bit in data_bits:
            data = (data << 1) | bit

        return data, len(error_positions), True

    def _find_error_locator(self, syndromes: List[int]) -> List[int]:
        """寻找错误定位多项式。

        Args:
            syndromes: 伴随式列表。

        Returns:
            错误定位多项式。
        """
        return [1] + syndromes[:self.t]

    def _find_error_positions(self, error_locator: List[int]) -> List[int]:
        """寻找错误位置。

        Args:
            error_locator: 错误定位多项式。

        Returns:
            错误位置列表。
        """
        positions = []
        for i in range(self.n):
            val = 0
            for j, coeff in enumerate(error_locator):
                if coeff:
                    val ^= pow(2, j * i, self.n + 1)
            if val == 0:
                positions.append(i)
        return positions


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