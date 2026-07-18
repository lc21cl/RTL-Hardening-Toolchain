import sys
import os
sys.path.insert(0, '.')

from hardening_pipeline import HardeningPipeline

def test_single_file():
    print('=== RTL单文件加固流程测试 ===')
    
    pipeline = HardeningPipeline(optimization_goal='balanced')
    input_file = 'test_mock_data/mixed_design.v'
    
    print('\n[1/8] 加载设计...')
    if pipeline.load_design(input_file):
        print('  OK 加载成功')
    else:
        print('  FAIL 加载失败')
        return False
    
    print('\n[2/8] 分析设计...')
    module_info = pipeline.analyze()
    print(f'  OK 分析完成: {len(module_info)} 个信号')
    for sig, info in module_info.items():
        print(f'    - {sig}: type={info["type"]}, width={info["width"]}')
    
    print('\n[3/8] 信号扫描...')
    scan_results = pipeline.scan_high_fanout_signals()
    print(f'  OK 扫描完成: {len(scan_results.get("high_fanout_signals", {}))} 个高扇出信号')
    
    print('\n[4/8] 脆弱性预测...')
    vuln_scores = pipeline.predict_vulnerability()
    print(f'  OK 预测完成: {len(vuln_scores)} 个寄存器')
    for sig, score in sorted(vuln_scores.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f'    - {sig}: {score:.4f}')
    
    print('\n[5/8] 策略路由...')
    pipeline.route_strategies()
    print('  OK 策略分配完成:')
    for sig, strategy in pipeline.strategy_map.items():
        sig_type = module_info[sig]['type']
        print(f'    - {sig} [{sig_type}] -> {strategy}')
    
    print('\n[6/8] AST变换...')
    pipeline.transform()
    print(f'  OK 变换完成: {len(pipeline.strategy_groups)} 个策略分组')
    
    print('\n[7/8] 输出加固代码...')
    output_dir = 'test_output_single'
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, 'mixed_design_hardened.v')
    if pipeline.output(output_file):
        print(f'  OK 输出成功: {output_file}')
        original_size = os.path.getsize(input_file)
        hardened_size = os.path.getsize(output_file)
        print(f'  文件大小: 原始={original_size} bytes -> 加固后={hardened_size} bytes')
    else:
        print('  FAIL 输出失败')
        return False
    
    print('\n[8/8] 验证分析...')
    verification = pipeline.formal_verify([output_file])
    print(f'  形式化验证: {verification.get("success", "N/A")}')
    compile_ok = pipeline.run_iverilog_check(output_file)
    print(f'  编译检查: {"通过" if compile_ok else "未通过或不可用"}')
    
    print('\n=== RTL单文件加固流程测试完成 ===')
    return True

def test_folder():
    print('\n\n=== RTL文件夹加固流程测试 ===')
    
    input_folder = 'test_mock_data'
    output_dir = 'test_output_folder'
    os.makedirs(output_dir, exist_ok=True)
    
    rtl_files = [f for f in os.listdir(input_folder) if f.endswith('.v')]
    print(f'  发现 {len(rtl_files)} 个RTL文件')
    
    for rtl_file in rtl_files[:2]:
        print(f'\n  处理文件: {rtl_file}')
        input_file = os.path.join(input_folder, rtl_file)
        pipeline = HardeningPipeline(optimization_goal='balanced')
        
        if pipeline.load_design(input_file):
            pipeline.analyze()
            pipeline.scan_high_fanout_signals()
            pipeline.predict_vulnerability()
            pipeline.route_strategies()
            pipeline.transform()
            
            base_name = os.path.splitext(rtl_file)[0]
            output_file = os.path.join(output_dir, f'{base_name}_hardened.v')
            if pipeline.output(output_file):
                print(f'    OK 加固完成: {output_file}')
            else:
                print(f'    FAIL 加固失败')
        else:
            print(f'    FAIL 加载失败')
    
    print('\n=== RTL文件夹加固流程测试完成 ===')
    return True

def test_dataset():
    print('\n\n=== RTL数据集加固流程测试 ===')
    
    dataset_file = 'datasets/example_dataset.jsonl'
    
    if not os.path.exists(dataset_file):
        print(f'  创建示例数据集: {dataset_file}')
        os.makedirs('datasets', exist_ok=True)
        with open(dataset_file, 'w', encoding='utf-8') as f:
            f.write('{"id": "design_1", "name": "Counter", "verilog": "module counter(input clk, input rst, output reg [7:0] count); always @(posedge clk) if(rst) count<=0; else count<=count+1; endmodule"}\n')
            f.write('{"id": "design_2", "name": "FIFO", "verilog": "module fifo(input clk, input rst, input [7:0] din, output [7:0] dout); reg [7:0] mem; always @(posedge clk) if(!rst) mem<=din; dout=mem; endmodule"}\n')
    
    print(f'  数据集文件: {dataset_file}')
    
    import json
    designs = []
    with open(dataset_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                designs.append(data)
            except:
                pass
    
    print(f'  发现 {len(designs)} 个设计')
    
    output_dir = 'test_output_dataset'
    os.makedirs(output_dir, exist_ok=True)
    
    for design in designs:
        design_id = design.get('id', 'unknown')
        design_name = design.get('name', 'unknown')
        verilog_code = design.get('verilog', design.get('code', ''))
        
        if not verilog_code:
            print(f'  跳过 {design_id}: 无RTL代码')
            continue
        
        print(f'\n  处理设计: {design_name}')
        
        temp_file = os.path.join(output_dir, f'{design_id}_temp.v')
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(verilog_code)
        
        pipeline = HardeningPipeline(optimization_goal='balanced')
        if pipeline.load_design(temp_file):
            pipeline.analyze()
            pipeline.scan_high_fanout_signals()
            pipeline.predict_vulnerability()
            pipeline.route_strategies()
            pipeline.transform()
            
            output_file = os.path.join(output_dir, f'{design_id}_hardened.v')
            if pipeline.output(output_file):
                print(f'    OK 加固完成')
            else:
                print(f'    FAIL 加固失败')
        else:
            print(f'    FAIL 加载失败')
        
        os.remove(temp_file)
    
    print('\n=== RTL数据集加固流程测试完成 ===')
    return True

if __name__ == '__main__':
    print('='*60)
    print('RTL加固工具全流程测试')
    print('='*60)
    
    results = []
    results.append(('RTL单文件', test_single_file()))
    results.append(('RTL文件夹', test_folder()))
    results.append(('RTL数据集', test_dataset()))
    
    print('\n' + '='*60)
    print('测试结果汇总')
    print('='*60)
    for name, success in results:
        status = 'PASS' if success else 'FAIL'
        print(f'  {name}: {status}')
    
    all_pass = all(s for _, s in results)
    sys.exit(0 if all_pass else 1)