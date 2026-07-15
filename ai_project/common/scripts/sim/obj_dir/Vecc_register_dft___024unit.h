// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design internal header
// See Vecc_register_dft.h for the primary calling header

#ifndef VERILATED_VECC_REGISTER_DFT___024UNIT_H_
#define VERILATED_VECC_REGISTER_DFT___024UNIT_H_  // guard

#include "verilated.h"


class Vecc_register_dft__Syms;

class alignas(VL_CACHE_LINE_BYTES) Vecc_register_dft___024unit final {
  public:

    // INTERNAL VARIABLES
    Vecc_register_dft__Syms* vlSymsp;
    const char* vlNamep;

    // CONSTRUCTORS
    Vecc_register_dft___024unit();
    ~Vecc_register_dft___024unit();
    void ctor(Vecc_register_dft__Syms* symsp, const char* namep);
    void dtor();
    VL_UNCOPYABLE(Vecc_register_dft___024unit);

    // INTERNAL METHODS
    void __Vconfigure(bool first);
};


#endif  // guard
