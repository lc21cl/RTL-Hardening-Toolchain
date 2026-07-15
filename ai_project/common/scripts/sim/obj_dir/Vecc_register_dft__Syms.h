// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Symbol table internal header
//
// Internal details; most calling programs do not need this header,
// unless using verilator public meta comments.

#ifndef VERILATED_VECC_REGISTER_DFT__SYMS_H_
#define VERILATED_VECC_REGISTER_DFT__SYMS_H_  // guard

#include "verilated.h"

// INCLUDE MODEL CLASS

#include "Vecc_register_dft.h"

// INCLUDE MODULE CLASSES
#include "Vecc_register_dft___024root.h"
#include "Vecc_register_dft___024unit.h"

// SYMS CLASS (contains all model state)
class alignas(VL_CACHE_LINE_BYTES) Vecc_register_dft__Syms final : public VerilatedSyms {
  public:
    // INTERNAL STATE
    Vecc_register_dft* const __Vm_modelp;
    VlDeleter __Vm_deleter;
    bool __Vm_didInit = false;

    // MODULE INSTANCE STATE
    Vecc_register_dft___024root    TOP;

    // CONSTRUCTORS
    Vecc_register_dft__Syms(VerilatedContext* contextp, const char* namep, Vecc_register_dft* modelp);
    ~Vecc_register_dft__Syms();

    // METHODS
    const char* name() const { return TOP.vlNamep; }
};

#endif  // guard
