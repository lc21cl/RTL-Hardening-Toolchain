// ====================================================
// sim_main.cpp — Verilator ECC 寄存器 DFT 测试平台
//
// 通过 ecc_register_dft 的故障注入端口 (fault_inject_en,
// fault_bit_mask, fault_parity_mask) 模拟 SEU,
// 无需 Verilator 不支持的 force/release 语句。
//
// 测试项:
//   1. 复位
//   2. 写入并回读 (单一值)
//   3. 多值写入验证
//   4. 单比特 SEU 纠正 (SEC)
//   5. 双比特 SEU 检测 (DED)
//   6. 校验位 SEU (数据不受影响)
//   7. SEU 后恢复写入
//   8. 长时间运行无误报
//   9. 全零模式 + 故障注入
//  10. 全一模式 + 故障注入
// ====================================================

#include <verilated.h>
#include <verilated_vcd_c.h>
#include "Vecc_register_dft.h"
#include <iostream>
#include <iomanip>
#include <cstdint>
#include <cstring>

vluint64_t sim_time = 0;
Vecc_register_dft *dut;
VerilatedVcdC *m_trace = nullptr;

// ---- Helper: toggle clock ----
void toggle_clk() {
    dut->clk = 0;
    dut->eval();
    sim_time++;
    if (m_trace) m_trace->dump(sim_time);

    dut->clk = 1;
    dut->eval();
    sim_time++;
    if (m_trace) m_trace->dump(sim_time);
}

// ---- Helper: apply reset ----
void apply_reset() {
    dut->rst_n = 0;
    dut->clk = 0;
    dut->en = 0;
    dut->fault_inject_en = 0;
    dut->fault_bit_mask = 0;
    dut->fault_parity_mask = 0;
    dut->d = 0;
    dut->eval();
    sim_time++;
    if (m_trace) m_trace->dump(sim_time);

    toggle_clk();  // posedge: reset takes effect

    dut->rst_n = 1;
    toggle_clk();  // release reset
}

// ---- Helper: write data to register ----
void write_data(uint32_t val) {
    dut->en = 1;
    dut->d = val;
    dut->fault_inject_en = 0;
    dut->fault_bit_mask = 0;
    dut->fault_parity_mask = 0;
    toggle_clk();  // posedge: data sampled

    dut->en = 0;
    toggle_clk();  // wait for decode to settle
}

// ---- Helper: inject fault via DFT ports ----
// 注意: inject_fault 在时钟上升沿将 code_reg XOR 掩码
// fault_inject_en=1 时, 写入的是 (original_codeword ^ mask)
// 因此写入的就是错误的码字
void inject_fault(uint32_t bit_mask, uint32_t parity_mask) {
    dut->en = 0;
    dut->fault_inject_en = 1;
    dut->fault_bit_mask = bit_mask;
    dut->fault_parity_mask = parity_mask;
    // 此时 d 不会被采样 (en=0), 但 DFT 逻辑会使 code_reg 被 XOR 掩码
    toggle_clk();

    dut->fault_inject_en = 0;
    dut->fault_bit_mask = 0;
    dut->fault_parity_mask = 0;
    toggle_clk();  // let decoder settle on corrupted codeword
}

// ---- Helper: read current q ----
uint32_t read_q() {
    return static_cast<uint32_t>(dut->q);
}

// ---- Helper: check result and count ----
void check(const char* name, bool condition, int& pass_cnt, int& fail_cnt) {
    if (condition) {
        pass_cnt++;
        std::cout << "  PASS: " << name << std::endl;
    } else {
        fail_cnt++;
        std::cout << "  FAIL: " << name
                  << " (q=0x" << std::hex << read_q()
                  << ", err=" << (dut->error_flag ? 1 : 0)
                  << ", cor=" << (dut->corrected ? 1 : 0)
                  << ")" << std::dec << std::endl;
    }
}

// ====================================================
int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);

    // Enable tracing if --trace passed
    bool trace_enabled = false;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--trace") == 0) {
            trace_enabled = true;
            break;
        }
    }

    dut = new Vecc_register_dft;

    if (trace_enabled) {
        Verilated::traceEverOn(true);
        m_trace = new VerilatedVcdC;
        dut->trace(m_trace, 99);
        m_trace->open("ecc_dft_trace.vcd");
    }

    int pass = 0, fail = 0;

    std::cout << "\n==========================================" << std::endl;
    std::cout << "ECC DFT Verification (Verilator)" << std::endl;
    std::cout << "==========================================" << std::endl;

    // ==========================================
    // Test 1: Reset
    // ==========================================
    std::cout << "\n--- Test 1: Reset ---" << std::endl;
    apply_reset();
    check("Reset: q == 0", read_q() == 0, pass, fail);
    check("Reset: no error", dut->error_flag == 0, pass, fail);
    check("Reset: not corrected", dut->corrected == 0, pass, fail);
    check("Reset: single_err_detected == 0", dut->single_err_detected == 0, pass, fail);
    check("Reset: double_err_detected == 0", dut->double_err_detected == 0, pass, fail);

    // ==========================================
    // Test 2: Write and read back (single value)
    // ==========================================
    std::cout << "\n--- Test 2: Write and Read 0xA5A5A5A5 ---" << std::endl;
    apply_reset();
    write_data(0xA5A5A5A5);
    check("Write 0xA5A5A5A5: q matches", read_q() == 0xA5A5A5A5, pass, fail);
    check("Write 0xA5A5A5A5: no error", dut->error_flag == 0, pass, fail);
    check("Write 0xA5A5A5A5: not corrected", dut->corrected == 0, pass, fail);

    // ==========================================
    // Test 3: Multiple write values
    // ==========================================
    std::cout << "\n--- Test 3: Multiple Writes ---" << std::endl;
    apply_reset();

    write_data(0x00000000);
    check("Write 0x00000000", read_q() == 0x00000000, pass, fail);

    write_data(0xFFFFFFFF);
    check("Write 0xFFFFFFFF", read_q() == 0xFFFFFFFF, pass, fail);

    write_data(0x12345678);
    check("Write 0x12345678", read_q() == 0x12345678, pass, fail);

    write_data(0xDEADBEEF);
    check("Write 0xDEADBEEF", read_q() == 0xDEADBEEF, pass, fail);

    write_data(0x55555555);
    check("Write 0x55555555", read_q() == 0x55555555, pass, fail);

    // ==========================================
    // Test 4: Single-bit SEU correction (SEC)
    // ==========================================
    std::cout << "\n--- Test 4: Single-bit SEU Correction ---" << std::endl;
    apply_reset();
    write_data(0xA5A5A5A5);

    // Inject single-bit fault: flip bit 3 of the data field
    // fault_bit_mask bit 3 = 1 -> flips data bit 3 in the stored codeword
    inject_fault(0x00000008, 0);

    check("SEC: corrected flag set", dut->corrected == 1, pass, fail);
    check("SEC: data corrected to original", read_q() == 0xA5A5A5A5, pass, fail);
    check("SEC: no double error", dut->error_flag == 0, pass, fail);
    check("SEC: single_err_detected set", dut->single_err_detected == 1, pass, fail);

    // ==========================================
    // Test 5: Double-bit SEU detection (DED)
    // ==========================================
    std::cout << "\n--- Test 5: Double-bit SEU Detection ---" << std::endl;
    apply_reset();
    write_data(0x55555555);

    // Inject two-bit fault: flip bits 0 and 3 of data field
    inject_fault(0x00000009, 0);

    check("DED: double error flag set", dut->error_flag == 1, pass, fail);
    check("DED: corrected not set (uncorrectable)", dut->corrected == 0, pass, fail);
    check("DED: double_err_detected set", dut->double_err_detected == 1, pass, fail);

    // ==========================================
    // Test 6: Parity-bit SEU (no data corruption)
    // ==========================================
    std::cout << "\n--- Test 6: Parity-bit SEU ---" << std::endl;
    apply_reset();
    write_data(0xFF00FF00);

    // Inject fault in parity bits (not data bits)
    // Flip a single parity bit via fault_parity_mask
    inject_fault(0, 0x01);  // flip parity bit 0

    // Data should still be correct — single-bit error in parity only
    // The syndrome will be non-zero, but data is fine.
    // For parity-only error: syndrome identifies the parity bit,
    // data is not corrected, but error is detected as corrected
    check("Parity SEU: data intact", read_q() == 0xFF00FF00, pass, fail);
    // A single parity bit flip is a correctable single-bit error
    check("Parity SEU: corrected flag", dut->corrected == 1, pass, fail);
    check("Parity SEU: no double error", dut->error_flag == 0, pass, fail);

    // ==========================================
    // Test 7: Recovery after SEU
    // ==========================================
    std::cout << "\n--- Test 7: Recovery After SEU ---" << std::endl;
    apply_reset();
    write_data(0xAAAAAAAA);

    // Inject single-bit fault
    inject_fault(0x00000100, 0);
    check("SEU recovery: corrected during fault", dut->corrected == 1, pass, fail);

    // Write new value — register should work normally again
    write_data(0xBBBBBBBB);
    check("SEU recovery: new write works", read_q() == 0xBBBBBBBB, pass, fail);
    check("SEU recovery: no error after rewrite", dut->error_flag == 0, pass, fail);
    check("SEU recovery: not corrected after rewrite", dut->corrected == 0, pass, fail);

    // ==========================================
    // Test 8: No spurious errors (long idle)
    // ==========================================
    std::cout << "\n--- Test 8: No Spurious Errors (100 cycles) ---" << std::endl;
    apply_reset();
    write_data(0xDEADBEEF);

    bool spurious = false;
    for (int i = 0; i < 100; i++) {
        toggle_clk();
        if (dut->error_flag || dut->corrected) {
            spurious = true;
            break;
        }
    }
    check("100 cycles: no false error flags", !spurious, pass, fail);
    check("100 cycles: data retained", read_q() == 0xDEADBEEF, pass, fail);

    // ==========================================
    // Test 9: All-zeros with fault injection
    // ==========================================
    std::cout << "\n--- Test 9: All-Zeros Pattern + Fault ---" << std::endl;
    apply_reset();
    write_data(0x00000000);
    check("Zeros: write OK", read_q() == 0x00000000, pass, fail);

    // Inject single-bit fault into all-zeros
    inject_fault(0x00000001, 0);
    // With one bit flipped, the stored codeword becomes incorrect
    // SEC should correct: syndrome != 0, gp != calc_gp -> single error
    check("Zeros+SEC: corrected flag", dut->corrected == 1, pass, fail);
    check("Zeros+SEC: corrected to zero", read_q() == 0x00000000, pass, fail);

    // ==========================================
    // Test 10: All-ones with fault injection
    // ==========================================
    std::cout << "\n--- Test 10: All-Ones Pattern + Fault ---" << std::endl;
    apply_reset();
    write_data(0xFFFFFFFF);
    check("Ones: write OK", read_q() == 0xFFFFFFFF, pass, fail);

    // Inject single-bit fault into all-ones
    inject_fault(0x00010000, 0);  // flip data bit 16
    check("Ones+SEC: corrected flag", dut->corrected == 1, pass, fail);
    check("Ones+SEC: corrected to ones", read_q() == 0xFFFFFFFF, pass, fail);

    // ==========================================
    // Summary
    // ==========================================
    std::cout << "\n==========================================" << std::endl;
    std::cout << "ECC DFT Tests: " << pass << " PASS, " << fail << " FAIL"
              << std::endl;
    std::cout << "==========================================" << std::endl;

    if (fail == 0) {
        std::cout << "ALL TESTS PASSED" << std::endl;
    } else {
        std::cout << "SOME TESTS FAILED" << std::endl;
    }

    if (m_trace) {
        m_trace->close();
        delete m_trace;
    }
    delete dut;

    return fail > 0 ? 1 : 0;
}
