// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design internal header
// See Vecc_register_dft.h for the primary calling header

#ifndef VERILATED_VECC_REGISTER_DFT___024ROOT_H_
#define VERILATED_VECC_REGISTER_DFT___024ROOT_H_  // guard

#include "verilated.h"


class Vecc_register_dft__Syms;

class alignas(VL_CACHE_LINE_BYTES) Vecc_register_dft___024root final {
  public:

    // DESIGN SPECIFIC STATE
    VL_IN8(clk,0,0);
    VL_IN8(rst_n,0,0);
    VL_IN8(en,0,0);
    VL_OUT8(error_flag,0,0);
    VL_OUT8(corrected,0,0);
    VL_IN8(fault_inject_en,0,0);
    VL_IN8(fault_parity_mask,4,0);
    VL_OUT8(single_err_detected,0,0);
    VL_OUT8(double_err_detected,0,0);
    CData/*0:0*/ __VstlFirstIteration;
    CData/*0:0*/ __VstlPhaseResult;
    CData/*0:0*/ __Vtrigprevexpr___TOP__clk__0;
    CData/*0:0*/ __Vtrigprevexpr___TOP__rst_n__0;
    CData/*0:0*/ __Vtrigprevexpr___TOP__en__0;
    CData/*0:0*/ __Vtrigprevexpr___TOP__fault_inject_en__0;
    CData/*4:0*/ __Vtrigprevexpr___TOP__fault_parity_mask__0;
    CData/*0:0*/ __VicoDidInit;
    CData/*0:0*/ __VicoPhaseResult;
    CData/*0:0*/ __Vtrigprevexpr___TOP__clk__1;
    CData/*0:0*/ __Vtrigprevexpr___TOP__rst_n__1;
    CData/*0:0*/ __VactPhaseResult;
    CData/*0:0*/ __VnbaPhaseResult;
    VL_IN(d,31,0);
    VL_OUT(q,31,0);
    VL_IN(fault_bit_mask,31,0);
    VL_OUT(corrected_data,31,0);
    IData/*31:0*/ __Vtrigprevexpr___TOP__d__0;
    IData/*31:0*/ __Vtrigprevexpr___TOP__fault_bit_mask__0;
    IData/*31:0*/ __VactIterCount;
    QData/*37:0*/ ecc_register_dft__DOT__code_reg;
    QData/*37:0*/ ecc_register_dft__DOT__encoded;
    VlUnpacked<QData/*63:0*/, 1> __VstlTriggered;
    VlUnpacked<QData/*63:0*/, 2> __VicoTriggered;
    VlUnpacked<QData/*63:0*/, 1> __VactTriggered;
    VlUnpacked<QData/*63:0*/, 1> __VnbaTriggered;

    // INTERNAL VARIABLES
    Vecc_register_dft__Syms* vlSymsp;
    const char* vlNamep;

    // CONSTRUCTORS
    Vecc_register_dft___024root(Vecc_register_dft__Syms* symsp, const char* namep);
    ~Vecc_register_dft___024root();
    VL_UNCOPYABLE(Vecc_register_dft___024root);

    // INTERNAL METHODS
    void __Vconfigure(bool first);
};


#endif  // guard
