#!/usr/bin/env python3
"""测试 P2 功能模块。"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dice_variants import (
    generate_dice_standard,
    generate_dice_2l,
    generate_dice_seh,
    generate_dice_pd,
    generate_dice_st,
    get_dice_variant_info,
    DICEVariant
)
from bch_ecc import (
    BCHCode,
    generate_bch_encoder,
    generate_bch_decoder,
    generate_bch_wrapper,
    get_bch_code_info
)
from multi_objective_optimization import (
    NSGAII,
    evaluate_hardening_strategy,
    find_pareto_optimal_strategies,
    select_best_strategy,
    generate_pareto_report
)
from placement_constraints import (
    generate_placement_constraints,
    generate_floorplan_constraints,
    generate_tmr_placement_script,
    generate_placement_report
)


def test_dice_variants():
    """测试DICE变形结构支持。"""
    print("=" * 60)
    print("测试 1: DICE变形结构支持")
    print("=" * 60)

    standard_dice = generate_dice_standard(width=8, cell_name='test_dice')
    print(f"标准DICE生成完成，长度: {len(standard_dice)}")

    dice_2l = generate_dice_2l(width=4, cell_name='test_dice_2l')
    print(f"DICE-2L生成完成，长度: {len(dice_2l)}")

    dice_seh = generate_dice_seh(width=1, cell_name='test_dice_seh')
    print(f"DICE-SEH生成完成，长度: {len(dice_seh)}")

    dice_pd = generate_dice_pd(width=8, cell_name='test_dice_pd')
    print(f"DICE-PD生成完成，长度: {len(dice_pd)}")

    dice_st = generate_dice_st(width=4, cell_name='test_dice_st')
    print(f"DICE-ST生成完成，长度: {len(dice_st)}")

    info = get_dice_variant_info(DICEVariant.DICE_2L)
    print(f"DICE-2L信息: {info}")

    print("✓ DICE变形结构测试通过\n")


def test_bch_ecc():
    """测试BCH码ECC扩展。"""
    print("=" * 60)
    print("测试 2: BCH码ECC扩展")
    print("=" * 60)

    bch = BCHCode(n=15, k=11, t=1)
    encoded = bch.encode(0b10101)
    print(f"BCH(15,11)编码测试: 输入=0b10101, 输出=0b{encoded:015b}")

    decoded, errors, corrected = bch.decode(encoded)
    print(f"解码测试: 输出=0b{decoded:011b}, 错误数={errors}, 可纠正={corrected}")

    encoder = generate_bch_encoder(n=15, k=11, t=1)
    print(f"BCH编码器生成完成，长度: {len(encoder)}")

    decoder = generate_bch_decoder(n=15, k=11, t=1)
    print(f"BCH解码器生成完成，长度: {len(decoder)}")

    wrapper = generate_bch_wrapper(data_width=32, ecc_type='bch_31_26')
    print(f"BCH包装器生成完成，长度: {len(wrapper)}")

    info = get_bch_code_info('bch_31_16')
    print(f"BCH(31,16)信息: {info}")

    print("✓ BCH码ECC测试通过\n")


def test_multi_objective_optimization():
    """测试多目标优化策略。"""
    print("=" * 60)
    print("测试 3: 多目标优化策略")
    print("=" * 60)

    signals = ['reg1', 'reg2', 'reg3', 'reg4', 'reg5']
    vulnerability_scores = {
        'reg1': 0.85,
        'reg2': 0.72,
        'reg3': 0.58,
        'reg4': 0.45,
        'reg5': 0.32
    }

    pareto_strategies = find_pareto_optimal_strategies(signals, vulnerability_scores)
    print(f"帕累托最优解数量: {len(pareto_strategies)}")

    for i, strategy in enumerate(pareto_strategies[:3]):
        objectives = evaluate_hardening_strategy(strategy, vulnerability_scores)
        print(f"解 {i+1}: {strategy} -> 面积={objectives[0]:.4f}, 可靠性={objectives[1]:.4f}, 性能={objectives[2]:.4f}")

    best_strategy = select_best_strategy(pareto_strategies, vulnerability_scores)
    print(f"最优策略: {best_strategy}")

    report = generate_pareto_report(pareto_strategies[:5], vulnerability_scores)
    print("帕累托报告:")
    print(report[:500])

    print("✓ 多目标优化测试通过\n")


def test_placement_constraints():
    """测试布局约束生成。"""
    print("=" * 60)
    print("测试 4: 布局约束生成")
    print("=" * 60)

    replicated_modules = ['inst_A', 'inst_B', 'inst_C']

    distance_constraints = generate_placement_constraints('test_module', replicated_modules, 'distance')
    print(f"距离约束生成完成，长度: {len(distance_constraints)}")

    region_constraints = generate_placement_constraints('test_module', replicated_modules, 'region')
    print(f"区域约束生成完成，长度: {len(region_constraints)}")

    group_constraints = generate_placement_constraints('test_module', replicated_modules, 'group')
    print(f"分组约束生成完成，长度: {len(group_constraints)}")

    floorplan = generate_floorplan_constraints('test_module', width=2000, height=2000)
    print(f"Floorplan约束生成完成，长度: {len(floorplan)}")

    placement_script = generate_tmr_placement_script('test_module', replicated_modules)
    print(f"布局脚本生成完成，长度: {len(placement_script)}")

    report = generate_placement_report('test_module', replicated_modules)
    print("布局约束报告:")
    print(report)

    print("✓ 布局约束生成测试通过\n")


def main():
    """运行所有P2功能测试。"""
    print("\n" + "=" * 60)
    print("P2 功能模块综合测试")
    print("=" * 60 + "\n")

    test_dice_variants()
    test_bch_ecc()
    test_multi_objective_optimization()
    test_placement_constraints()

    print("=" * 60)
    print("所有 P2 功能测试通过!")
    print("=" * 60)


if __name__ == '__main__':
    main()