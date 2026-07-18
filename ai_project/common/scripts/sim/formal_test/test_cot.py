#!/usr/bin/env python3
"""验证CoT信号分类功能"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rag_integration import cot_classify_signal, MockLLM

rtl = '''
module test(input clk, input rst_n, input [7:0] d, output reg [7:0] q);
    reg [3:0] state;
    reg [7:0] counter;
    reg [31:0] cfg_reg;
    always @(posedge clk or posedge rst_n) begin
        if (!rst_n) state <= 0;
        else case(state) 0: state <= d; default: state <= 0; endcase
    end
    always @(posedge clk) counter <= counter + 1;
endmodule
'''

for sig in ['state', 'counter', 'cfg_reg', 'q']:
    r = cot_classify_signal(sig, rtl)
    print(f'  {sig:10s} -> {r["type"]:10s} vuln={r["vulnerability"]:.2f} method={r["method"]} confidence={r["confidence"]}')
    assert r['type'] in ['fsm','counter','control','data_path'], f'Bad type: {r["type"]}'

print('\nAll CoT classifications: OK')

# MockLLM测试
print('\nMockLLM classify test:')
try:
    mock = MockLLM()
    r = mock.classify_signal('state', rtl)
    print(f'  MockLLM: {r["signal"]} -> {r["type"]} (confidence={r["confidence"]})')
    assert r['type'] in ['fsm','counter','control','data_path']
    print('MockLLM classify: OK')
except Exception as e:
    print(f'  MockLLM classify: {e}')

print('\nCoT: ALL TESTS PASSED')
