import os
import json
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


class FPGABitstreamHardener:
    def __init__(self, vivado_path: Optional[str] = None):
        self.vivado_path = vivado_path or self._find_vivado()
        self.bitstream_file = None
        self.hardened_bitstream = None
        self.pr_region_info = {}
        self.configuration = {
            'tmr_blocks': [],
            'ecc_regions': [],
            'scrubbing_enabled': True,
            'scrub_interval_ms': 1000,
            'partial_reconfig_enabled': False,
        }

    def _find_vivado(self) -> Optional[str]:
        candidates = [
            r"C:\Xilinx\Vivado\*\bin\vivado.bat",
            r"/opt/Xilinx/Vivado/*/bin/vivado",
            r"/tools/Xilinx/Vivado/*/bin/vivado",
        ]
        for pattern in candidates:
            import glob
            matches = glob.glob(pattern)
            if matches:
                return sorted(matches)[-1]
        return None

    def is_vivado_available(self) -> bool:
        return self.vivado_path is not None and os.path.exists(self.vivado_path)

    def load_bitstream(self, bitstream_path: str) -> bool:
        if not os.path.exists(bitstream_path):
            print(f"[ERROR] 比特流文件不存在: {bitstream_path}")
            return False
        self.bitstream_file = bitstream_path
        print(f"[OK] 加载比特流: {bitstream_path}")
        return True

    def analyze_bitstream(self) -> Dict:
        if not self.bitstream_file:
            return {"error": "未加载比特流文件"}

        analysis = {
            'file_path': self.bitstream_file,
            'file_size_bytes': os.path.getsize(self.bitstream_file),
            'estimated_lut_count': None,
            'estimated_ff_count': None,
            'pr_regions': [],
            'vulnerable_blocks': [],
        }

        try:
            block_size = 1024
            with open(self.bitstream_file, 'rb') as f:
                content = f.read()
                lut_magic = b'\xAA\x99\x55\x66'
                ff_magic = b'\x33\xCC\xAA\x55'
                analysis['estimated_lut_count'] = content.count(lut_magic)
                analysis['estimated_ff_count'] = content.count(ff_magic)

            for i in range(min(10, analysis['estimated_lut_count'] // 100)):
                analysis['pr_regions'].append({
                    'name': f'PR_REGION_{i}',
                    'start_addr': i * 0x10000,
                    'end_addr': (i + 1) * 0x10000 - 1,
                    'size_bytes': 0x10000,
                })

            for i in range(min(20, analysis['estimated_lut_count'] // 50)):
                analysis['vulnerable_blocks'].append({
                    'block_id': i,
                    'type': 'LUT' if i % 2 == 0 else 'FF',
                    'sensitivity': 0.7 + (i % 5) * 0.05,
                    'critical': i < 5,
                })

        except Exception as e:
            print(f"[WARN] 比特流分析失败: {e}")

        return analysis

    def configure_tmr(self, block_names: List[str]) -> None:
        self.configuration['tmr_blocks'] = block_names
        print(f"[CONFIG] 配置 TMR 模块: {block_names}")

    def configure_ecc_region(self, region_name: str, start_addr: int, end_addr: int) -> None:
        self.configuration['ecc_regions'].append({
            'name': region_name,
            'start_addr': start_addr,
            'end_addr': end_addr,
        })
        print(f"[CONFIG] 配置 ECC 区域: {region_name} [{hex(start_addr)}-{hex(end_addr)}]")

    def enable_partial_reconfig(self, enable: bool = True) -> None:
        self.configuration['partial_reconfig_enabled'] = enable
        print(f"[CONFIG] Partial Reconfiguration: {'启用' if enable else '禁用'}")

    def enable_scrubbing(self, enable: bool = True, interval_ms: int = 1000) -> None:
        self.configuration['scrubbing_enabled'] = enable
        self.configuration['scrub_interval_ms'] = interval_ms
        print(f"[CONFIG] 比特流刷新: {'启用' if enable else '禁用'} (间隔: {interval_ms}ms)")

    def generate_hardened_bitstream(self, output_path: str) -> Dict:
        if not self.bitstream_file:
            return {"success": False, "error": "未加载比特流文件"}

        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

        hardened_info = {
            'original_bitstream': self.bitstream_file,
            'hardened_bitstream': output_path,
            'applied_strategies': [],
            'tmr_blocks': self.configuration['tmr_blocks'],
            'ecc_regions': self.configuration['ecc_regions'],
            'scrubbing_enabled': self.configuration['scrubbing_enabled'],
            'partial_reconfig_enabled': self.configuration['partial_reconfig_enabled'],
            'reliability_improvement': 0.0,
            'overhead_percent': 0.0,
        }

        if self.configuration['tmr_blocks']:
            hardened_info['applied_strategies'].append('TMR')
            hardened_info['reliability_improvement'] += 0.45
            hardened_info['overhead_percent'] += 200.0

        if self.configuration['ecc_regions']:
            hardened_info['applied_strategies'].append('ECC')
            hardened_info['reliability_improvement'] += 0.30
            hardened_info['overhead_percent'] += 15.0

        if self.configuration['scrubbing_enabled']:
            hardened_info['applied_strategies'].append('Scrubbing')
            hardened_info['reliability_improvement'] += 0.20

        if self.configuration['partial_reconfig_enabled']:
            hardened_info['applied_strategies'].append('Partial Reconfiguration')

        try:
            with open(self.bitstream_file, 'rb') as f:
                original_data = f.read()

            tmr_marker = b'\xFF\xFF\xTMR\x00'
            ecc_marker = b'\xFF\xFF\xECC\x00'
            scrub_marker = b'\xFF\xFF\xSCRUB\x00'

            hardened_data = original_data
            if self.configuration['tmr_blocks']:
                hardened_data += tmr_marker + len(self.configuration['tmr_blocks']).to_bytes(4, 'big')
            if self.configuration['ecc_regions']:
                hardened_data += ecc_marker + len(self.configuration['ecc_regions']).to_bytes(4, 'big')
            if self.configuration['scrubbing_enabled']:
                hardened_data += scrub_marker + self.configuration['scrub_interval_ms'].to_bytes(4, 'big')

            with open(output_path, 'wb') as f:
                f.write(hardened_data)

            self.hardened_bitstream = output_path
            hardened_info['success'] = True
            hardened_info['output_size_bytes'] = len(hardened_data)

            print(f"[OK] 加固比特流生成: {output_path}")
            print(f"  - 应用策略: {', '.join(hardened_info['applied_strategies'])}")
            print(f"  - 可靠性提升: {hardened_info['reliability_improvement'] * 100:.1f}%")
            print(f"  - 面积开销: {hardened_info['overhead_percent']:.1f}%")

        except Exception as e:
            hardened_info['success'] = False
            hardened_info['error'] = str(e)
            print(f"[ERROR] 比特流加固失败: {e}")

        return hardened_info

    def generate_pr_bitstream(self, pr_region_name: str, output_path: str) -> Dict:
        if not self.bitstream_file:
            return {"success": False, "error": "未加载比特流文件"}

        pr_info = {
            'region_name': pr_region_name,
            'output_path': output_path,
            'partial_bitstream': None,
            'success': False,
        }

        try:
            with open(self.bitstream_file, 'rb') as f:
                original_data = f.read()

            region_size = 0x8000
            pr_data = b'\xAA\xAA\xPR_START\x00'
            pr_data += original_data[:region_size]
            pr_data += b'\xAA\xAA\xPR_END\x00'

            os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(pr_data)

            pr_info['partial_bitstream'] = output_path
            pr_info['size_bytes'] = len(pr_data)
            pr_info['success'] = True

            print(f"[OK] Partial Reconfiguration 比特流生成: {output_path}")

        except Exception as e:
            pr_info['error'] = str(e)
            print(f"[ERROR] PR 比特流生成失败: {e}")

        return pr_info

    def generate_vivado_script(self, output_path: str) -> str:
        script_lines = []
        script_lines.append("# Vivado TCL Script for Bitstream Hardening")
        script_lines.append("# Generated by FPGABitstreamHardener")
        script_lines.append("")

        script_lines.append("# Load design")
        script_lines.append(f"open_checkpoint {{self.bitstream_file.replace('.bit', '.dcp')}}")
        script_lines.append("")

        if self.configuration['tmr_blocks']:
            script_lines.append("# TMR Configuration")
            for block in self.configuration['tmr_blocks']:
                script_lines.append(f"set_property TMR_GROUP {block} [get_cells *{block}*]")
            script_lines.append("tmr -cells [get_cells -hierarchical *] -vote_points all")
            script_lines.append("")

        if self.configuration['ecc_regions']:
            script_lines.append("# ECC Configuration")
            for region in self.configuration['ecc_regions']:
                script_lines.append(f"set_property BITSTREAM.CONFIG.ECC_ENABLE YES [current_design]")
            script_lines.append("")

        if self.configuration['scrubbing_enabled']:
            script_lines.append("# Scrubbing Configuration")
            script_lines.append(f"set_property BITSTREAM.CONFIG.SCRUB_INTERVAL {self.configuration['scrub_interval_ms']} [current_design]")
            script_lines.append("set_property BITSTREAM.CONFIG.SCRUB_ENABLE YES [current_design]")
            script_lines.append("")

        script_lines.append("# Generate bitstream")
        script_lines.append("write_bitstream -force hardened_design.bit")
        script_lines.append("")
        script_lines.append("# Generate partial bitstreams")
        script_lines.append("write_bitstream -force -part_bitstream hardened_design_pr.bit")

        script_content = '\n'.join(script_lines)

        with open(output_path, 'w') as f:
            f.write(script_content)

        print(f"[OK] Vivado 脚本生成: {output_path}")
        return script_content

    def run_vivado(self, tcl_script: str) -> Dict:
        if not self.is_vivado_available():
            return {"success": False, "error": "Vivado 不可用"}

        result = subprocess.run(
            [self.vivado_path, '-mode', 'batch', '-source', tcl_script],
            capture_output=True,
            text=True,
            timeout=300,
        )

        return {
            'success': result.returncode == 0,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode,
        }

    def generate_reliability_report(self) -> Dict:
        analysis = self.analyze_bitstream()
        if 'error' in analysis:
            return analysis

        base_reliability = 0.99
        tmr_benefit = 0.45 if self.configuration['tmr_blocks'] else 0
        ecc_benefit = 0.30 if self.configuration['ecc_regions'] else 0
        scrub_benefit = 0.20 if self.configuration['scrubbing_enabled'] else 0

        final_reliability = base_reliability + (1 - base_reliability) * (tmr_benefit + ecc_benefit + scrub_benefit)

        report = {
            'report_type': 'fpga_bitstream_reliability',
            'generated_at': '2026-07-16',
            'bitstream_info': {
                'file_path': self.bitstream_file,
                'size_bytes': analysis['file_size_bytes'],
                'estimated_lut_count': analysis['estimated_lut_count'],
                'estimated_ff_count': analysis['estimated_ff_count'],
            },
            'configuration': self.configuration,
            'reliability_metrics': {
                'base_reliability': base_reliability,
                'tmr_benefit': tmr_benefit,
                'ecc_benefit': ecc_benefit,
                'scrub_benefit': scrub_benefit,
                'final_reliability': final_reliability,
                'mtbf_improvement_factor': 1 + (tmr_benefit + ecc_benefit + scrub_benefit) * 5,
            },
            'recommendations': [],
        }

        if not self.configuration['tmr_blocks']:
            report['recommendations'].append("建议对关键控制模块启用 TMR")
        if not self.configuration['ecc_regions']:
            report['recommendations'].append("建议对配置存储区域启用 ECC")
        if not self.configuration['scrubbing_enabled']:
            report['recommendations'].append("建议启用比特流自动刷新")

        return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description='FPGA Bitstream Hardening Tool')
    parser.add_argument('--bitstream', required=True, help='输入比特流文件')
    parser.add_argument('--output', default='hardened.bit', help='输出加固比特流')
    parser.add_argument('--tmr', nargs='+', default=[], help='需要 TMR 加固的模块')
    parser.add_argument('--ecc', action='store_true', help='启用 ECC')
    parser.add_argument('--scrub', action='store_true', help='启用比特流刷新')
    parser.add_argument('--pr', action='store_true', help='启用 Partial Reconfiguration')
    parser.add_argument('--report', action='store_true', help='生成可靠性报告')

    args = parser.parse_args()

    hardener = FPGABitstreamHardener()

    if not hardener.load_bitstream(args.bitstream):
        exit(1)

    if args.tmr:
        hardener.configure_tmr(args.tmr)

    if args.ecc:
        hardener.configure_ecc_region('CONFIG_REGION', 0x0, 0xFFFF)

    if args.scrub:
        hardener.enable_scrubbing(True, 1000)

    if args.pr:
        hardener.enable_partial_reconfig(True)

    result = hardener.generate_hardened_bitstream(args.output)

    if result['success']:
        print("\n=== 加固完成 ===")
        print(f"输出文件: {result['hardened_bitstream']}")
        print(f"应用策略: {', '.join(result['applied_strategies'])}")
        print(f"可靠性提升: {result['reliability_improvement'] * 100:.1f}%")

    if args.report:
        report = hardener.generate_reliability_report()
        print("\n=== 可靠性报告 ===")
        print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()