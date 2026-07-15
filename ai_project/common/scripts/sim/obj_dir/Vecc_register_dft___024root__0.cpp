// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vecc_register_dft.h for the primary calling header

#include "Vecc_register_dft__pch.h"

bool Vecc_register_dft___024root___trigger_anySet__ico(const VlUnpacked<QData/*63:0*/, 2> &in) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vecc_register_dft___024root___trigger_anySet__ico\n"); );
    // Locals
    IData/*31:0*/ n;
    // Body
    n = 0U;
    do {
        if (in[n]) {
            return (1U);
        }
        n = ((IData)(1U) + n);
    } while ((2U > n));
    return (0U);
}

void Vecc_register_dft___024root___ico_sequent__TOP__0(Vecc_register_dft___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vecc_register_dft___024root___ico_sequent__TOP__0\n"); );
    Vecc_register_dft__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Locals
    CData/*4:0*/ ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s;
    ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s = 0;
    CData/*4:0*/ ecc_register_dft__DOT__u_enc__DOT__hp;
    ecc_register_dft__DOT__u_enc__DOT__hp = 0;
    CData/*4:0*/ __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__Vfuncout;
    __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__Vfuncout = 0;
    IData/*31:0*/ __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d;
    __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d = 0;
    // Body
    __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d 
        = vlSelfRef.d;
    ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s = 0U;
    if ((1U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (1U ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((2U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (2U ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((4U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (3U ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((8U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (4U ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00000010U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (5U ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00000020U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (6U ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00000040U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (7U ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00000080U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (8U ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00000100U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (9U ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00000200U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x0aU ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00000400U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x0bU ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00000800U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x0cU ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00001000U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x0dU ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00002000U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x0eU ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00004000U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x0fU ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00008000U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x10U ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00010000U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x11U ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00020000U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x12U ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00040000U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x13U ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00080000U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x14U ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00100000U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x15U ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00200000U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x16U ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00400000U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x17U ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x00800000U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x18U ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x01000000U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x19U ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x02000000U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x1aU ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x04000000U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x1bU ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x08000000U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x1cU ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x10000000U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x1dU ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x20000000U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x1eU ^ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s));
    }
    if ((0x40000000U & __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__d)) {
        ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s 
            = (0x0000001fU & (~ (IData)(ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s)));
    }
    __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__Vfuncout 
        = ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__Vstatic__s;
    ecc_register_dft__DOT__u_enc__DOT__hp = __Vfunc_ecc_register_dft__DOT__u_enc__DOT__hamming_syndrome__0__Vfuncout;
    vlSelfRef.ecc_register_dft__DOT__encoded = (((QData)((IData)(
                                                                 (1U 
                                                                  & (VL_REDXOR_32(vlSelfRef.d) 
                                                                     ^ 
                                                                     VL_REDXOR_8(ecc_register_dft__DOT__u_enc__DOT__hp))))) 
                                                 << 0x00000025U) 
                                                | (((QData)((IData)(ecc_register_dft__DOT__u_enc__DOT__hp)) 
                                                    << 0x00000020U) 
                                                   | (QData)((IData)(vlSelfRef.d))));
}

#ifdef VL_DEBUG
VL_ATTR_COLD void Vecc_register_dft___024root___dump_triggers__ico(const VlUnpacked<QData/*63:0*/, 2> &triggers, const std::string &tag);
#endif  // VL_DEBUG

bool Vecc_register_dft___024root___eval_phase__ico(Vecc_register_dft___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vecc_register_dft___024root___eval_phase__ico\n"); );
    Vecc_register_dft__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Locals
    CData/*0:0*/ __VicoExecute;
    // Body
    {
        // Inlined CFunc: _eval_triggers_vec__ico
        vlSelfRef.__VicoTriggered[0U] = (QData)((IData)(
                                                        (((((IData)(vlSelfRef.fault_parity_mask) 
                                                            != (IData)(vlSelfRef.__Vtrigprevexpr___TOP__fault_parity_mask__0)) 
                                                           << 6U) 
                                                          | (((vlSelfRef.fault_bit_mask 
                                                               != vlSelfRef.__Vtrigprevexpr___TOP__fault_bit_mask__0) 
                                                              << 5U) 
                                                             | (((IData)(vlSelfRef.fault_inject_en) 
                                                                 != (IData)(vlSelfRef.__Vtrigprevexpr___TOP__fault_inject_en__0)) 
                                                                << 4U))) 
                                                         | ((((vlSelfRef.d 
                                                               != vlSelfRef.__Vtrigprevexpr___TOP__d__0) 
                                                              << 3U) 
                                                             | (((IData)(vlSelfRef.en) 
                                                                 != (IData)(vlSelfRef.__Vtrigprevexpr___TOP__en__0)) 
                                                                << 2U)) 
                                                            | ((((IData)(vlSelfRef.rst_n) 
                                                                 != (IData)(vlSelfRef.__Vtrigprevexpr___TOP__rst_n__0)) 
                                                                << 1U) 
                                                               | ((IData)(vlSelfRef.clk) 
                                                                  != (IData)(vlSelfRef.__Vtrigprevexpr___TOP__clk__0)))))));
        vlSelfRef.__Vtrigprevexpr___TOP__clk__0 = vlSelfRef.clk;
        vlSelfRef.__Vtrigprevexpr___TOP__rst_n__0 = vlSelfRef.rst_n;
        vlSelfRef.__Vtrigprevexpr___TOP__en__0 = vlSelfRef.en;
        vlSelfRef.__Vtrigprevexpr___TOP__d__0 = vlSelfRef.d;
        vlSelfRef.__Vtrigprevexpr___TOP__fault_inject_en__0 
            = vlSelfRef.fault_inject_en;
        vlSelfRef.__Vtrigprevexpr___TOP__fault_bit_mask__0 
            = vlSelfRef.fault_bit_mask;
        vlSelfRef.__Vtrigprevexpr___TOP__fault_parity_mask__0 
            = vlSelfRef.fault_parity_mask;
        if (VL_UNLIKELY(((1U & (~ (IData)(vlSelfRef.__VicoDidInit)))))) {
            vlSelfRef.__VicoDidInit = 1U;
            vlSelfRef.__VicoTriggered[0U] = (1ULL | vlSelfRef.__VicoTriggered[0U]);
            vlSelfRef.__VicoTriggered[0U] = (2ULL | vlSelfRef.__VicoTriggered[0U]);
            vlSelfRef.__VicoTriggered[0U] = (4ULL | vlSelfRef.__VicoTriggered[0U]);
            vlSelfRef.__VicoTriggered[0U] = (8ULL | vlSelfRef.__VicoTriggered[0U]);
            vlSelfRef.__VicoTriggered[0U] = (0x0000000000000010ULL 
                                             | vlSelfRef.__VicoTriggered[0U]);
            vlSelfRef.__VicoTriggered[0U] = (0x0000000000000020ULL 
                                             | vlSelfRef.__VicoTriggered[0U]);
            vlSelfRef.__VicoTriggered[0U] = (0x0000000000000040ULL 
                                             | vlSelfRef.__VicoTriggered[0U]);
        }
    }
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vecc_register_dft___024root___dump_triggers__ico(vlSelfRef.__VicoTriggered, "ico"s);
    }
#endif
    __VicoExecute = Vecc_register_dft___024root___trigger_anySet__ico(vlSelfRef.__VicoTriggered);
    if (__VicoExecute) {
        {
            // Inlined CFunc: _eval_ico
            if ((8ULL & vlSelfRef.__VicoTriggered[0U])) {
                Vecc_register_dft___024root___ico_sequent__TOP__0(vlSelf);
            }
        }
    }
    return (__VicoExecute);
}

bool Vecc_register_dft___024root___trigger_anySet__act(const VlUnpacked<QData/*63:0*/, 1> &in) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vecc_register_dft___024root___trigger_anySet__act\n"); );
    // Locals
    IData/*31:0*/ n;
    // Body
    n = 0U;
    do {
        if (in[n]) {
            return (1U);
        }
        n = ((IData)(1U) + n);
    } while ((1U > n));
    return (0U);
}

void Vecc_register_dft___024root___nba_sequent__TOP__0(Vecc_register_dft___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vecc_register_dft___024root___nba_sequent__TOP__0\n"); );
    Vecc_register_dft__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Locals
    CData/*4:0*/ ecc_register_dft__DOT__u_dec__DOT__syndrome;
    ecc_register_dft__DOT__u_dec__DOT__syndrome = 0;
    IData/*31:0*/ ecc_register_dft__DOT__u_dec__DOT__corrected;
    ecc_register_dft__DOT__u_dec__DOT__corrected = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_0;
    __VdfgRegularize_h6e95ff9d_0_0 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_1;
    __VdfgRegularize_h6e95ff9d_0_1 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_2;
    __VdfgRegularize_h6e95ff9d_0_2 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_3;
    __VdfgRegularize_h6e95ff9d_0_3 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_4;
    __VdfgRegularize_h6e95ff9d_0_4 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_5;
    __VdfgRegularize_h6e95ff9d_0_5 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_6;
    __VdfgRegularize_h6e95ff9d_0_6 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_7;
    __VdfgRegularize_h6e95ff9d_0_7 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_8;
    __VdfgRegularize_h6e95ff9d_0_8 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_9;
    __VdfgRegularize_h6e95ff9d_0_9 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_10;
    __VdfgRegularize_h6e95ff9d_0_10 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_11;
    __VdfgRegularize_h6e95ff9d_0_11 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_12;
    __VdfgRegularize_h6e95ff9d_0_12 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_13;
    __VdfgRegularize_h6e95ff9d_0_13 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_14;
    __VdfgRegularize_h6e95ff9d_0_14 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_15;
    __VdfgRegularize_h6e95ff9d_0_15 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_16;
    __VdfgRegularize_h6e95ff9d_0_16 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_17;
    __VdfgRegularize_h6e95ff9d_0_17 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_18;
    __VdfgRegularize_h6e95ff9d_0_18 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_19;
    __VdfgRegularize_h6e95ff9d_0_19 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_20;
    __VdfgRegularize_h6e95ff9d_0_20 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_21;
    __VdfgRegularize_h6e95ff9d_0_21 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_22;
    __VdfgRegularize_h6e95ff9d_0_22 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_23;
    __VdfgRegularize_h6e95ff9d_0_23 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_24;
    __VdfgRegularize_h6e95ff9d_0_24 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_25;
    __VdfgRegularize_h6e95ff9d_0_25 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_26;
    __VdfgRegularize_h6e95ff9d_0_26 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_27;
    __VdfgRegularize_h6e95ff9d_0_27 = 0;
    CData/*4:0*/ __VdfgRegularize_h6e95ff9d_0_28;
    __VdfgRegularize_h6e95ff9d_0_28 = 0;
    CData/*0:0*/ __VdfgRegularize_h6e95ff9d_0_29;
    __VdfgRegularize_h6e95ff9d_0_29 = 0;
    // Body
    if (vlSelfRef.rst_n) {
        if (vlSelfRef.fault_inject_en) {
            vlSelfRef.ecc_register_dft__DOT__code_reg 
                = (vlSelfRef.ecc_register_dft__DOT__encoded 
                   ^ (((QData)((IData)(vlSelfRef.fault_parity_mask)) 
                       << 0x00000020U) | (QData)((IData)(vlSelfRef.fault_bit_mask))));
        } else if (vlSelfRef.en) {
            vlSelfRef.ecc_register_dft__DOT__code_reg 
                = vlSelfRef.ecc_register_dft__DOT__encoded;
        }
    } else {
        vlSelfRef.ecc_register_dft__DOT__code_reg = 0ULL;
    }
    __VdfgRegularize_h6e95ff9d_0_29 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x00000025U))) 
                                       != (1U & VL_REDXOR_64(
                                                             (0x0000001fffffffffULL 
                                                              & vlSelfRef.ecc_register_dft__DOT__code_reg))));
    __VdfgRegularize_h6e95ff9d_0_0 = ((1U & (IData)(
                                                    (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                     >> 1U)))
                                       ? (2U ^ (1U 
                                                & (- (IData)(
                                                             (1U 
                                                              & (IData)(vlSelfRef.ecc_register_dft__DOT__code_reg))))))
                                       : (1U & (- (IData)(
                                                          (1U 
                                                           & (IData)(vlSelfRef.ecc_register_dft__DOT__code_reg))))));
    __VdfgRegularize_h6e95ff9d_0_1 = ((1U & (IData)(
                                                    (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                     >> 2U)))
                                       ? (3U ^ (IData)(__VdfgRegularize_h6e95ff9d_0_0))
                                       : (IData)(__VdfgRegularize_h6e95ff9d_0_0));
    __VdfgRegularize_h6e95ff9d_0_2 = ((1U & (IData)(
                                                    (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                     >> 3U)))
                                       ? (4U ^ (IData)(__VdfgRegularize_h6e95ff9d_0_1))
                                       : (IData)(__VdfgRegularize_h6e95ff9d_0_1));
    __VdfgRegularize_h6e95ff9d_0_3 = ((1U & (IData)(
                                                    (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                     >> 4U)))
                                       ? (5U ^ (IData)(__VdfgRegularize_h6e95ff9d_0_2))
                                       : (IData)(__VdfgRegularize_h6e95ff9d_0_2));
    __VdfgRegularize_h6e95ff9d_0_4 = ((1U & (IData)(
                                                    (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                     >> 5U)))
                                       ? (6U ^ (IData)(__VdfgRegularize_h6e95ff9d_0_3))
                                       : (IData)(__VdfgRegularize_h6e95ff9d_0_3));
    __VdfgRegularize_h6e95ff9d_0_5 = ((1U & (IData)(
                                                    (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                     >> 6U)))
                                       ? (7U ^ (IData)(__VdfgRegularize_h6e95ff9d_0_4))
                                       : (IData)(__VdfgRegularize_h6e95ff9d_0_4));
    __VdfgRegularize_h6e95ff9d_0_6 = ((1U & (IData)(
                                                    (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                     >> 7U)))
                                       ? (8U ^ (IData)(__VdfgRegularize_h6e95ff9d_0_5))
                                       : (IData)(__VdfgRegularize_h6e95ff9d_0_5));
    __VdfgRegularize_h6e95ff9d_0_7 = ((1U & (IData)(
                                                    (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                     >> 8U)))
                                       ? (9U ^ (IData)(__VdfgRegularize_h6e95ff9d_0_6))
                                       : (IData)(__VdfgRegularize_h6e95ff9d_0_6));
    __VdfgRegularize_h6e95ff9d_0_8 = ((1U & (IData)(
                                                    (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                     >> 9U)))
                                       ? (0x0aU ^ (IData)(__VdfgRegularize_h6e95ff9d_0_7))
                                       : (IData)(__VdfgRegularize_h6e95ff9d_0_7));
    __VdfgRegularize_h6e95ff9d_0_9 = ((1U & (IData)(
                                                    (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                     >> 0x0000000aU)))
                                       ? (0x0bU ^ (IData)(__VdfgRegularize_h6e95ff9d_0_8))
                                       : (IData)(__VdfgRegularize_h6e95ff9d_0_8));
    __VdfgRegularize_h6e95ff9d_0_10 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x0000000bU)))
                                        ? (0x0cU ^ (IData)(__VdfgRegularize_h6e95ff9d_0_9))
                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_9));
    __VdfgRegularize_h6e95ff9d_0_11 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x0000000cU)))
                                        ? (0x0dU ^ (IData)(__VdfgRegularize_h6e95ff9d_0_10))
                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_10));
    __VdfgRegularize_h6e95ff9d_0_12 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x0000000dU)))
                                        ? (0x0eU ^ (IData)(__VdfgRegularize_h6e95ff9d_0_11))
                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_11));
    __VdfgRegularize_h6e95ff9d_0_13 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x0000000eU)))
                                        ? (0x0fU ^ (IData)(__VdfgRegularize_h6e95ff9d_0_12))
                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_12));
    __VdfgRegularize_h6e95ff9d_0_14 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x0000000fU)))
                                        ? (0x10U ^ (IData)(__VdfgRegularize_h6e95ff9d_0_13))
                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_13));
    __VdfgRegularize_h6e95ff9d_0_15 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x00000010U)))
                                        ? (0x11U ^ (IData)(__VdfgRegularize_h6e95ff9d_0_14))
                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_14));
    __VdfgRegularize_h6e95ff9d_0_16 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x00000011U)))
                                        ? (0x12U ^ (IData)(__VdfgRegularize_h6e95ff9d_0_15))
                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_15));
    __VdfgRegularize_h6e95ff9d_0_17 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x00000012U)))
                                        ? (0x13U ^ (IData)(__VdfgRegularize_h6e95ff9d_0_16))
                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_16));
    __VdfgRegularize_h6e95ff9d_0_18 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x00000013U)))
                                        ? (0x14U ^ (IData)(__VdfgRegularize_h6e95ff9d_0_17))
                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_17));
    __VdfgRegularize_h6e95ff9d_0_19 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x00000014U)))
                                        ? (0x15U ^ (IData)(__VdfgRegularize_h6e95ff9d_0_18))
                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_18));
    __VdfgRegularize_h6e95ff9d_0_20 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x00000015U)))
                                        ? (0x16U ^ (IData)(__VdfgRegularize_h6e95ff9d_0_19))
                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_19));
    __VdfgRegularize_h6e95ff9d_0_21 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x00000016U)))
                                        ? (0x17U ^ (IData)(__VdfgRegularize_h6e95ff9d_0_20))
                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_20));
    __VdfgRegularize_h6e95ff9d_0_22 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x00000017U)))
                                        ? (0x18U ^ (IData)(__VdfgRegularize_h6e95ff9d_0_21))
                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_21));
    __VdfgRegularize_h6e95ff9d_0_23 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x00000018U)))
                                        ? (0x19U ^ (IData)(__VdfgRegularize_h6e95ff9d_0_22))
                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_22));
    __VdfgRegularize_h6e95ff9d_0_24 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x00000019U)))
                                        ? (0x1aU ^ (IData)(__VdfgRegularize_h6e95ff9d_0_23))
                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_23));
    __VdfgRegularize_h6e95ff9d_0_25 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x0000001aU)))
                                        ? (0x1bU ^ (IData)(__VdfgRegularize_h6e95ff9d_0_24))
                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_24));
    __VdfgRegularize_h6e95ff9d_0_26 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x0000001bU)))
                                        ? (0x1cU ^ (IData)(__VdfgRegularize_h6e95ff9d_0_25))
                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_25));
    __VdfgRegularize_h6e95ff9d_0_27 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x0000001cU)))
                                        ? (0x1dU ^ (IData)(__VdfgRegularize_h6e95ff9d_0_26))
                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_26));
    __VdfgRegularize_h6e95ff9d_0_28 = ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x0000001dU)))
                                        ? (0x1eU ^ (IData)(__VdfgRegularize_h6e95ff9d_0_27))
                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_27));
    ecc_register_dft__DOT__u_dec__DOT__syndrome = (0x0000001fU 
                                                   & ((IData)(
                                                              (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                               >> 0x00000020U)) 
                                                      ^ 
                                                      ((1U 
                                                        & (IData)(
                                                                  (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                                   >> 0x0000001eU)))
                                                        ? 
                                                       (~ (IData)(__VdfgRegularize_h6e95ff9d_0_28))
                                                        : (IData)(__VdfgRegularize_h6e95ff9d_0_28))));
    vlSelfRef.error_flag = (1U & ((0U == (IData)(ecc_register_dft__DOT__u_dec__DOT__syndrome))
                                   ? (IData)(__VdfgRegularize_h6e95ff9d_0_29)
                                   : (~ (IData)(__VdfgRegularize_h6e95ff9d_0_29))));
    vlSelfRef.corrected = (1U & (~ ((0U == (IData)(ecc_register_dft__DOT__u_dec__DOT__syndrome)) 
                                    | ((1U & (IData)(
                                                     (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                      >> 0x00000025U))) 
                                       == (1U & VL_REDXOR_64(
                                                             (0x0000001fffffffffULL 
                                                              & vlSelfRef.ecc_register_dft__DOT__code_reg)))))));
    ecc_register_dft__DOT__u_dec__DOT__corrected = (IData)(vlSelfRef.ecc_register_dft__DOT__code_reg);
    if ((0U != (IData)(ecc_register_dft__DOT__u_dec__DOT__syndrome))) {
        if (((1U & (IData)((vlSelfRef.ecc_register_dft__DOT__code_reg 
                            >> 0x00000025U))) != (1U 
                                                  & VL_REDXOR_64(
                                                                 (0x0000001fffffffffULL 
                                                                  & vlSelfRef.ecc_register_dft__DOT__code_reg))))) {
            if ((1U <= (IData)(ecc_register_dft__DOT__u_dec__DOT__syndrome))) {
                ecc_register_dft__DOT__u_dec__DOT__corrected 
                    = (((~ ((IData)(1U) << (0x0000001fU 
                                            & ((IData)(ecc_register_dft__DOT__u_dec__DOT__syndrome) 
                                               - (IData)(1U))))) 
                        & ecc_register_dft__DOT__u_dec__DOT__corrected) 
                       | (0x00000000ffffffffULL & (
                                                   (1U 
                                                    & (~ (IData)(
                                                                 (vlSelfRef.ecc_register_dft__DOT__code_reg 
                                                                  >> 
                                                                  (0x0000001fU 
                                                                   & ((IData)(ecc_register_dft__DOT__u_dec__DOT__syndrome) 
                                                                      - (IData)(1U))))))) 
                                                   << 
                                                   (0x0000001fU 
                                                    & ((IData)(ecc_register_dft__DOT__u_dec__DOT__syndrome) 
                                                       - (IData)(1U))))));
            }
        }
    }
    vlSelfRef.double_err_detected = vlSelfRef.error_flag;
    vlSelfRef.single_err_detected = vlSelfRef.corrected;
    vlSelfRef.q = ecc_register_dft__DOT__u_dec__DOT__corrected;
    vlSelfRef.corrected_data = ecc_register_dft__DOT__u_dec__DOT__corrected;
}

void Vecc_register_dft___024root___trigger_orInto__act_vec_vec(VlUnpacked<QData/*63:0*/, 1> &out, const VlUnpacked<QData/*63:0*/, 1> &in) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vecc_register_dft___024root___trigger_orInto__act_vec_vec\n"); );
    // Locals
    IData/*31:0*/ n;
    // Body
    n = 0U;
    do {
        out[n] = (out[n] | in[n]);
        n = ((IData)(1U) + n);
    } while ((0U >= n));
}

#ifdef VL_DEBUG
VL_ATTR_COLD void Vecc_register_dft___024root___dump_triggers__act(const VlUnpacked<QData/*63:0*/, 1> &triggers, const std::string &tag);
#endif  // VL_DEBUG

bool Vecc_register_dft___024root___eval_phase__act(Vecc_register_dft___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vecc_register_dft___024root___eval_phase__act\n"); );
    Vecc_register_dft__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    {
        // Inlined CFunc: _eval_triggers_vec__act
        vlSelfRef.__VactTriggered[0U] = (QData)((IData)(
                                                        ((((~ (IData)(vlSelfRef.rst_n)) 
                                                           & (IData)(vlSelfRef.__Vtrigprevexpr___TOP__rst_n__1)) 
                                                          << 1U) 
                                                         | ((IData)(vlSelfRef.clk) 
                                                            & (~ (IData)(vlSelfRef.__Vtrigprevexpr___TOP__clk__1))))));
        vlSelfRef.__Vtrigprevexpr___TOP__clk__1 = vlSelfRef.clk;
        vlSelfRef.__Vtrigprevexpr___TOP__rst_n__1 = vlSelfRef.rst_n;
    }
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vecc_register_dft___024root___dump_triggers__act(vlSelfRef.__VactTriggered, "act"s);
    }
#endif
    Vecc_register_dft___024root___trigger_orInto__act_vec_vec(vlSelfRef.__VnbaTriggered, vlSelfRef.__VactTriggered);
    return (0U);
}

void Vecc_register_dft___024root___trigger_clear__act(VlUnpacked<QData/*63:0*/, 1> &out) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vecc_register_dft___024root___trigger_clear__act\n"); );
    // Locals
    IData/*31:0*/ n;
    // Body
    n = 0U;
    do {
        out[n] = 0ULL;
        n = ((IData)(1U) + n);
    } while ((1U > n));
}

bool Vecc_register_dft___024root___eval_phase__nba(Vecc_register_dft___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vecc_register_dft___024root___eval_phase__nba\n"); );
    Vecc_register_dft__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Locals
    CData/*0:0*/ __VnbaExecute;
    // Body
    __VnbaExecute = Vecc_register_dft___024root___trigger_anySet__act(vlSelfRef.__VnbaTriggered);
    if (__VnbaExecute) {
        {
            // Inlined CFunc: _eval_nba
            if ((3ULL & vlSelfRef.__VnbaTriggered[0U])) {
                Vecc_register_dft___024root___nba_sequent__TOP__0(vlSelf);
            }
        }
        Vecc_register_dft___024root___trigger_clear__act(vlSelfRef.__VnbaTriggered);
    }
    return (__VnbaExecute);
}

void Vecc_register_dft___024root___eval(Vecc_register_dft___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vecc_register_dft___024root___eval\n"); );
    Vecc_register_dft__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Locals
    IData/*31:0*/ __VicoIterCount;
    IData/*31:0*/ __VnbaIterCount;
    // Body
    __VicoIterCount = 0U;
    do {
        if (VL_UNLIKELY(((0x00002710U < __VicoIterCount)))) {
#ifdef VL_DEBUG
            Vecc_register_dft___024root___dump_triggers__ico(vlSelfRef.__VicoTriggered, "ico"s);
#endif
            VL_FATAL_MT("d:\\learning\\AI_RESEARCH\\ai_project\\common\\scripts\\test_mock_data\\ecc_register_dft.v", 147, "", "DIDNOTCONVERGE: Input combinational region did not converge after '--converge-limit' of 10000 tries");
        }
        __VicoIterCount = ((IData)(1U) + __VicoIterCount);
        vlSelfRef.__VicoPhaseResult = Vecc_register_dft___024root___eval_phase__ico(vlSelf);
    } while (vlSelfRef.__VicoPhaseResult);
    __VnbaIterCount = 0U;
    do {
        if (VL_UNLIKELY(((0x00002710U < __VnbaIterCount)))) {
#ifdef VL_DEBUG
            Vecc_register_dft___024root___dump_triggers__act(vlSelfRef.__VnbaTriggered, "nba"s);
#endif
            VL_FATAL_MT("d:\\learning\\AI_RESEARCH\\ai_project\\common\\scripts\\test_mock_data\\ecc_register_dft.v", 147, "", "DIDNOTCONVERGE: NBA region did not converge after '--converge-limit' of 10000 tries");
        }
        __VnbaIterCount = ((IData)(1U) + __VnbaIterCount);
        vlSelfRef.__VactIterCount = 0U;
        do {
            if (VL_UNLIKELY(((0x00002710U < vlSelfRef.__VactIterCount)))) {
#ifdef VL_DEBUG
                Vecc_register_dft___024root___dump_triggers__act(vlSelfRef.__VactTriggered, "act"s);
#endif
                VL_FATAL_MT("d:\\learning\\AI_RESEARCH\\ai_project\\common\\scripts\\test_mock_data\\ecc_register_dft.v", 147, "", "DIDNOTCONVERGE: Active region did not converge after '--converge-limit' of 10000 tries");
            }
            vlSelfRef.__VactIterCount = ((IData)(1U) 
                                         + vlSelfRef.__VactIterCount);
            vlSelfRef.__VactPhaseResult = Vecc_register_dft___024root___eval_phase__act(vlSelf);
        } while (vlSelfRef.__VactPhaseResult);
        vlSelfRef.__VnbaPhaseResult = Vecc_register_dft___024root___eval_phase__nba(vlSelf);
    } while (vlSelfRef.__VnbaPhaseResult);
}

#ifdef VL_DEBUG
void Vecc_register_dft___024root___eval_debug_assertions(Vecc_register_dft___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vecc_register_dft___024root___eval_debug_assertions\n"); );
    Vecc_register_dft__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    if (VL_UNLIKELY(((vlSelfRef.clk & 0xfeU)))) {
        Verilated::overWidthError("clk");
    }
    if (VL_UNLIKELY(((vlSelfRef.rst_n & 0xfeU)))) {
        Verilated::overWidthError("rst_n");
    }
    if (VL_UNLIKELY(((vlSelfRef.en & 0xfeU)))) {
        Verilated::overWidthError("en");
    }
    if (VL_UNLIKELY(((vlSelfRef.fault_inject_en & 0xfeU)))) {
        Verilated::overWidthError("fault_inject_en");
    }
    if (VL_UNLIKELY(((vlSelfRef.fault_parity_mask & 0xe0U)))) {
        Verilated::overWidthError("fault_parity_mask");
    }
}
#endif  // VL_DEBUG
