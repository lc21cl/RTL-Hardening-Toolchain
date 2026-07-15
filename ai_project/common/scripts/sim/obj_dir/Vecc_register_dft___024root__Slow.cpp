// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vecc_register_dft.h for the primary calling header

#include "Vecc_register_dft__pch.h"

void Vecc_register_dft___024root___ctor_var_reset(Vecc_register_dft___024root* vlSelf);

Vecc_register_dft___024root::Vecc_register_dft___024root(Vecc_register_dft__Syms* symsp, const char* namep)
 {
    vlSymsp = symsp;
    vlNamep = strdup(namep);
    // Reset structure values
    Vecc_register_dft___024root___ctor_var_reset(this);
}

void Vecc_register_dft___024root::__Vconfigure(bool first) {
    (void)first;  // Prevent unused variable warning
}

Vecc_register_dft___024root::~Vecc_register_dft___024root() {
    VL_DO_DANGLING(std::free(const_cast<char*>(vlNamep)), vlNamep);
}
