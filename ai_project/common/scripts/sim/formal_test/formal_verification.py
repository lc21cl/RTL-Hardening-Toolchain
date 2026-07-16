#!/usr/bin/env python3
"""formal_verification.py — 形式化验证集成模块

集成 SymbiYosys 进行形式化验证，验证加固后的功能正确性。

用法:
    from formal_verification import FormalVerifier

    verifier = FormalVerifier()
    result = verifier.verify(rtl_file, sva_file)
    report = verifier.get_report()
"""

import os
import subprocess
import re
from typing import List, Dict, Any, Optional


class FormalVerifier:
    """形式化验证器。

    集成 SymbiYosys 进行形式化验证。
    """

    def __init__(self):
        """初始化形式化验证器。"""
        self._yosys_path = self._find_yosys()
        self._sby_path = self._find_sby()
        self._reports: List[Dict[str, Any]] = []

    def _find_yosys(self) -> Optional[str]:
        """查找 Yosys 路径。

        Returns:
            Yosys 路径
        """
        for path in os.environ.get("PATH", "").split(os.pathsep):
            yosys_bin = os.path.join(path, "yosys.exe" if os.name == "nt" else "yosys")
            if os.path.isfile(yosys_bin):
                return yosys_bin
        return None

    def _find_sby(self) -> Optional[str]:
        """查找 SymbiYosys 路径。

        Returns:
            SymbiYosys 路径
        """
        for path in os.environ.get("PATH", "").split(os.pathsep):
            sby_bin = os.path.join(path, "sby.exe" if os.name == "nt" else "sby")
            if os.path.isfile(sby_bin):
                return sby_bin
        return None

    def is_available(self) -> bool:
        """检查形式化验证工具是否可用。

        Returns:
            是否可用
        """
        return self._yosys_path is not None and self._sby_path is not None

    def create_sby_config(
        self,
        rtl_files: List[str],
        sva_files: List[str],
        output_dir: str = "formal_output",
    ) -> str:
        """创建 SymbiYosys 配置文件。

        Args:
            rtl_files: RTL 文件列表
            sva_files: SVA 文件列表
            output_dir: 输出目录

        Returns:
            配置文件路径
        """
        config_content = f"""; SymbiYosys configuration
[options]
mode bmc
depth 20

[engines]
smtbmc yices2

[script]
"""

        for rtl_file in rtl_files:
            config_content += f"read_verilog {rtl_file}\n"

        config_content += "hierarchy -check -top top\n"
        config_content += "prep -top top\n"

        for sva_file in sva_files:
            config_content += f"read_sva {sva_file}\n"

        config_content += """
[files]
"""

        for rtl_file in rtl_files:
            config_content += f"{rtl_file}\n"

        for sva_file in sva_files:
            config_content += f"{sva_file}\n"

        os.makedirs(output_dir, exist_ok=True)
        config_path = os.path.join(output_dir, "formal.sby")

        with open(config_path, "w", encoding="utf-8") as f:
            f.write(config_content)

        return config_path

    def verify(
        self,
        rtl_files: List[str],
        sva_files: Optional[List[str]] = None,
        output_dir: str = "formal_output",
    ) -> Dict[str, Any]:
        """执行形式化验证。

        Args:
            rtl_files: RTL 文件列表
            sva_files: SVA 文件列表
            output_dir: 输出目录

        Returns:
            验证结果
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "SymbiYosys not found. Please install oss-cad-suite.",
            }

        sva_files = sva_files or []

        config_path = self.create_sby_config(rtl_files, sva_files, output_dir)

        try:
            result = subprocess.run(
                [self._sby_path, config_path],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(config_path),
                timeout=300,
            )

            return self._parse_sby_output(result)
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Verification timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _parse_sby_output(self, result: subprocess.CompletedProcess) -> Dict[str, Any]:
        """解析 SymbiYosys 输出。

        Args:
            result: 子进程执行结果

        Returns:
            解析结果
        """
        output = result.stdout + result.stderr

        status = "unknown"
        if "PASS" in output:
            status = "pass"
        elif "FAIL" in output:
            status = "fail"
        elif "UNKNOWN" in output:
            status = "unknown"

        properties = []
        for line in output.split("\n"):
            prop_match = re.search(r"Property\s+(\w+)\s*:\s*(PASS|FAIL|UNKNOWN)", line)
            if prop_match:
                properties.append({
                    "name": prop_match.group(1),
                    "status": prop_match.group(2),
                })

        return {
            "success": True,
            "status": status,
            "properties": properties,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode,
        }

    def simple_verify(self, rtl_content: str) -> Dict[str, Any]:
        """简单验证（无 SVA）。

        Args:
            rtl_content: RTL 代码

        Returns:
            验证结果
        """
        temp_dir = "formal_temp"
        os.makedirs(temp_dir, exist_ok=True)

        rtl_path = os.path.join(temp_dir, "test.v")
        with open(rtl_path, "w", encoding="utf-8") as f:
            f.write(rtl_content)

        try:
            result = subprocess.run(
                [self._yosys_path, "-p", "read_verilog test.v; hierarchy -check; stat"],
                capture_output=True,
                text=True,
                cwd=temp_dir,
                timeout=60,
            )

            success = result.returncode == 0 and "error" not in result.stderr.lower()

            cell_count = 0
            for line in result.stdout.split("\n"):
                cell_match = re.search(r"(\d+)\s+cells", line)
                if cell_match:
                    cell_count = int(cell_match.group(1))

            return {
                "success": success,
                "cell_count": cell_count,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
            }
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    def get_report(self) -> Dict[str, Any]:
        """获取验证报告。

        Returns:
            验证报告
        """
        pass_count = sum(1 for r in self._reports if r.get("status") == "pass")
        fail_count = sum(1 for r in self._reports if r.get("status") == "fail")

        return {
            "total_verifications": len(self._reports),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "reports": self._reports,
        }


if __name__ == "__main__":
    verifier = FormalVerifier()

    print("=== Formal Verification Test ===")
    print(f"Yosys available: {verifier._yosys_path}")
    print(f"SymbiYosys available: {verifier._sby_path}")
    print(f"Overall available: {verifier.is_available()}")

    test_rtl = """
module top(
    input clk,
    input rst,
    input [7:0] din,
    output [7:0] dout
);
    reg [7:0] buffer;
    always @(posedge clk or posedge rst) begin
        if (rst) buffer <= 0;
        else buffer <= din;
    end
    assign dout = buffer;
endmodule
"""

    if verifier.is_available():
        print("\nRunning simple verification...")
        result = verifier.simple_verify(test_rtl)
        print(f"Success: {result['success']}")
        print(f"Cell count: {result['cell_count']}")
    else:
        print("\nSymbiYosys not available. Skipping verification test.")
        print("Install with: pip install oss-cad-suite or download from https://github.com/YosysHQ/oss-cad-suite-build")
