// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vecc_register_dft.h for the primary calling header

#include "Vecc_register_dft__pch.h"


Vecc_register_dft___024unit::Vecc_register_dft___024unit() = default;
Vecc_register_dft___024unit::~Vecc_register_dft___024unit() = default;

void Vecc_register_dft___024unit::ctor(Vecc_register_dft__Syms* symsp, const char* namep) {
    vlSymsp = symsp;
    vlNamep = strdup(Verilated::catName(vlSymsp->name(), namep));
    // Reset structure values
}

void Vecc_register_dft___024unit::__Vconfigure(bool first) {
    (void)first;  // Prevent unused variable warning
}

void Vecc_register_dft___024unit::dtor() {
    VL_DO_DANGLING(std::free(const_cast<char*>(vlNamep)), vlNamep);
}
