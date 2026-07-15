#!/usr/bin/env python3
"""
End-to-end test for RAG + Auto-Repair pipeline.
Tests: KB → RAG → Verification → Auto-Repair
"""
import sys, os, glob, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 62)
print("  E2E TEST: RAG + Auto-Repair Pipeline")
print("=" * 62)

# ── Part 1: Knowledge Base ──────────────────────────────────────────────
print("\n[1] Knowledge Base")
from hardening_knowledge_base import KnowledgeBase, PatternRetriever

kb = KnowledgeBase()
kb.load_defaults()
print(f"  Patterns: {len(kb.patterns)}")
print(f"  Categories: {kb.list_categories()}")

# Test search
results = kb.search("triple modular")
print(f"  Search 'triple modular': {len(results)} results")
for r in results[:2]:
    print(f"    - {r.name} (cat={r.category}, overhead={r.area_overhead}x)")

# Test filter
tmr = kb.get('TMR')
assert tmr is not None, "TMR pattern not found!"
tmr_filled = tmr.fill_template(module_name='test_adder', signal_width=8)
print(f"  TMR template rendered: {len(tmr_filled.splitlines())} lines")
print(f"    First line: {tmr_filled.splitlines()[0]}")

# Test retriever
retriever = PatternRetriever(kb)
retrieved = retriever.retrieve("counter with error detection", top_k=3)
print(f"  Retriever query: {len(retrieved)} results")
for r in retrieved:
    print(f"    - {r[0].name} (score={r[1]:.3f})")

# ── Part 2: RAG Engine ─────────────────────────────────────────────────
print("\n[2] RAG Engine")
from rag_integration import RAGEngine, analyze_design_for_hardening

# Mock test
engine = RAGEngine(llm_backend='mock')
rl = engine.load_knowledge_base()
print(f"  KB loaded: {rl}")

# Test context building
mock_vuln = {
    'num_vulnerable': 5,
    'num_nodes': 20,
    'vulnerable_nodes': [{'node_id': i, 'score': 0.85 - i*0.05} for i in range(5)],
    'scores': [0.85, 0.80, 0.75, 0.70, 0.65],
}
mock_design = {
    'module_name': 'test_counter',
    'signals': [{'name': 'counter_out', 'width': 8, 'type': 'reg'}],
    'signal_width': 8,
}
context = engine._build_context(mock_vuln, top_k=2)
print(f"  Context built: {len(context)} chars")
prompt = engine._build_prompt(context, mock_design)
print(f"  Prompt built: {len(prompt)} chars")

# Generate hardened RTL
result = engine.generate_hardened_rtl(mock_design, mock_vuln)
print(f"  Generated RTL: {len(result.splitlines())} lines")
print(f"    First line: {result.splitlines()[0]}")

# ── Part 3: Verification Engine ────────────────────────────────────────
print("\n[3] Verification Engine")
from verification_engine import VerificationEngine

verifier = VerificationEngine(verbose=True)
mock_rtl = "D:\\learning\\AI_RESEARCH\\ai_project\\common\\scripts\\test_mock_data\\dice_template.v"
if os.path.exists(mock_rtl):
    syn_result = verifier.syntax_check(mock_rtl)
    print(f"  Syntax check: {'PASSED' if syn_result['passed'] else 'FAILED'}")
    print(f"    Warnings: {len(syn_result.get('warnings', []))}")
    props = verifier.check_design_properties(mock_rtl)
    print(f"  Design props: modules={props.get('modules',0)}, ports={props.get('ports',0)}")

# ── Part 4: Auto-Repair ────────────────────────────────────────────────
print("\n[4] Auto-Repair")
from auto_repair import AutoRepairEngine, hardening_with_repair, generate_repair_report

repairer = AutoRepairEngine(verifier=verifier, max_iterations=3, verbose=True)
repair_result = repairer.repair(mock_rtl)
print(f"  Repair result: passed={repair_result['passed']}, iterations={repair_result['iterations']}")

# Report
report = generate_repair_report(repair_result)
print(f"  Report length: {len(report)} chars")

# ── Part 5: End-to-end hardening_with_repair ───────────────────────────
print("\n[5] End-to-end: hardening_with_repair")
from gnn_inference import GNNInference

e2 = GNNInference(threshold=0.05)
if e2.load_model('data/models/SAGE2-Lite-64.pth'):
    blifs = glob.glob('blifs/*.blif')
    if blifs:
        v_result = e2.infer_from_blif(blifs[0])
        # Build mock vulnerability result with correct keys
        mock_vuln_result = {
            'source_file': blifs[0],
            'num_vulnerable': v_result['num_vulnerable'],
            'num_nodes': v_result['num_nodes'],
            'all_vulnerable_nodes': v_result.get('all_vulnerable_nodes', []),
            'max_score': v_result.get('max_score', 0),
            'mean_score': v_result.get('mean_score', 0),
        }
        e2e_result = hardening_with_repair(
            mock_rtl, mock_vuln_result, rag_engine=engine
        )
        print(f"  E2E result: passed={e2e_result['passed']}, iterations={e2e_result['iterations']}")
        print(f"  Hardened RTL: {len(e2e_result.get('hardened_rtl','').splitlines())} lines")

print(f"\n{'=' * 62}")
print(f"  ALL TESTS COMPLETED")
print(f"{'=' * 62}")
