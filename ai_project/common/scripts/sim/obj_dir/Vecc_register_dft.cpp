// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Model implementation (design independent parts)

#include "Vecc_register_dft__pch.h"

//============================================================
// Constructors

Vecc_register_dft::Vecc_register_dft(VerilatedContext* _vcontextp__, const char* _vcname__)
    : VerilatedModel{*_vcontextp__}
    , vlSymsp{new Vecc_register_dft__Syms(contextp(), _vcname__, this)}
    , clk{vlSymsp->TOP.clk}
    , rst_n{vlSymsp->TOP.rst_n}
    , en{vlSymsp->TOP.en}
    , error_flag{vlSymsp->TOP.error_flag}
    , corrected{vlSymsp->TOP.corrected}
    , fault_inject_en{vlSymsp->TOP.fault_inject_en}
    , fault_parity_mask{vlSymsp->TOP.fault_parity_mask}
    , single_err_detected{vlSymsp->TOP.single_err_detected}
    , double_err_detected{vlSymsp->TOP.double_err_detected}
    , d{vlSymsp->TOP.d}
    , q{vlSymsp->TOP.q}
    , fault_bit_mask{vlSymsp->TOP.fault_bit_mask}
    , corrected_data{vlSymsp->TOP.corrected_data}
    , rootp{&(vlSymsp->TOP)}
{
    // Register model with the context
    contextp()->addModel(this);
}

Vecc_register_dft::Vecc_register_dft(const char* _vcname__)
    : Vecc_register_dft(Verilated::threadContextp(), _vcname__)
{
}

//============================================================
// Destructor

Vecc_register_dft::~Vecc_register_dft() {
    delete vlSymsp;
}

//============================================================
// Evaluation function

#ifdef VL_DEBUG
void Vecc_register_dft___024root___eval_debug_assertions(Vecc_register_dft___024root* vlSelf);
#endif  // VL_DEBUG
void Vecc_register_dft___024root___eval_static(Vecc_register_dft___024root* vlSelf);
void Vecc_register_dft___024root___eval_initial(Vecc_register_dft___024root* vlSelf);
void Vecc_register_dft___024root___eval_settle(Vecc_register_dft___024root* vlSelf);
void Vecc_register_dft___024root___eval(Vecc_register_dft___024root* vlSelf);

void Vecc_register_dft::eval_step() {
    VL_DEBUG_IF(VL_DBG_MSGF("+++++TOP Evaluate Vecc_register_dft::eval_step\n"); );
#ifdef VL_DEBUG
    // Debug assertions
    Vecc_register_dft___024root___eval_debug_assertions(&(vlSymsp->TOP));
#endif  // VL_DEBUG
    vlSymsp->__Vm_deleter.deleteAll();
    if (VL_UNLIKELY(!vlSymsp->__Vm_didInit)) {
        VL_DEBUG_IF(VL_DBG_MSGF("+ Initial\n"););
        Vecc_register_dft___024root___eval_static(&(vlSymsp->TOP));
        Vecc_register_dft___024root___eval_initial(&(vlSymsp->TOP));
        Vecc_register_dft___024root___eval_settle(&(vlSymsp->TOP));
        vlSymsp->__Vm_didInit = true;
    }
    VL_DEBUG_IF(VL_DBG_MSGF("+ Eval\n"););
    Vecc_register_dft___024root___eval(&(vlSymsp->TOP));
    // Evaluate cleanup
    Verilated::endOfEval(vlSymsp->__Vm_evalMsgQp);
}

//============================================================
// Events and timing
bool Vecc_register_dft::eventsPending() { return false; }

uint64_t Vecc_register_dft::nextTimeSlot() {
    VL_FATAL_MT(__FILE__, __LINE__, "", "No delays in the design");
    return 0;
}

//============================================================
// Utilities

const char* Vecc_register_dft::name() const {
    return vlSymsp->name();
}

//============================================================
// Invoke final blocks

void Vecc_register_dft___024root___eval_final(Vecc_register_dft___024root* vlSelf);

VL_ATTR_COLD void Vecc_register_dft::final() {
    contextp()->executingFinal(true);
    Vecc_register_dft___024root___eval_final(&(vlSymsp->TOP));
    contextp()->executingFinal(false);
}

//============================================================
// Implementations of abstract methods from VerilatedModel

const char* Vecc_register_dft::hierName() const { return vlSymsp->name(); }
const char* Vecc_register_dft::modelName() const { return "Vecc_register_dft"; }
unsigned Vecc_register_dft::threads() const { return 1; }
void Vecc_register_dft::prepareClone() const { contextp()->prepareClone(); }
void Vecc_register_dft::atClone() const {
    contextp()->threadPoolpOnClone();
}
