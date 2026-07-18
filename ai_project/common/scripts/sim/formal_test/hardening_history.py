#!/usr/bin/env python3
"""hardening_history.py — 加固效果对比库"""
import os, json, time, copy
from typing import Dict, List, Optional, Any

class HardeningHistory:
    """加固历史记录管理器"""
    
    def __init__(self, storage_dir: str = None):
        self.storage_dir = storage_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 
            '..', '..', 'output', 'history'
        )
        os.makedirs(self.storage_dir, exist_ok=True)
        self.history_file = os.path.join(self.storage_dir, 'hardening_history.json')
        self.records = self._load()
        print(f"[HISTORY] Loaded {len(self.records)} records from {self.history_file}")
    
    def _load(self) -> List[Dict]:
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[HISTORY] Load error: {e}")
        return []
    
    def _save(self):
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self.records, f, indent=2, ensure_ascii=False)
        print(f"[HISTORY] Saved {len(self.records)} records to {self.history_file}")
    
    def add_record(self, design_file: str, strategy_map: Dict, 
                   metrics: Dict, output_file: str, workflow_type: str = 'single') -> str:
        record_id = f"R{int(time.time())}"
        record = {
            'id': record_id,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'design_file': os.path.basename(design_file),
            'workflow_type': workflow_type,
            'strategy_map': {k: v for k, v in strategy_map.items()},
            'metrics': metrics,
            'output_file': output_file,
        }
        self.records.insert(0, record)
        if len(self.records) > 100:  # 最多保留100条
            self.records = self.records[:100]
        self._save()
        print(f"[HISTORY] Added record {record_id} for {os.path.basename(design_file)}")
        return record_id
    
    def get_all_records(self) -> List[Dict]:
        return self.records
    
    def get_record(self, record_id: str) -> Optional[Dict]:
        for r in self.records:
            if r['id'] == record_id:
                return r
        return None
    
    def compare_records(self, record_ids: List[str]) -> Dict:
        records = [self.get_record(rid) for rid in record_ids]
        records = [r for r in records if r]
        metrics_keys = set()
        for r in records:
            metrics_keys.update(r.get('metrics', {}).keys())
        
        comparison = {
            'records': [],
            'metrics_comparison': {},
        }
        for key in sorted(metrics_keys):
            values = []
            for r in records:
                v = r.get('metrics', {}).get(key, 'N/A')
                values.append(v)
            comparison['metrics_comparison'][key] = values
        
        for r in records:
            comparison['records'].append({
                'id': r['id'],
                'timestamp': r['timestamp'],
                'design': r['design_file'],
                'strategy_count': len(r.get('strategy_map', {})),
                'metrics': r.get('metrics', {}),
            })
        
        print(f"[HISTORY] Compared {len(records)} records")
        return comparison
    
    def delete_record(self, record_id: str) -> bool:
        for i, r in enumerate(self.records):
            if r['id'] == record_id:
                del self.records[i]
                self._save()
                print(f"[HISTORY] Deleted record {record_id}")
                return True
        return False
    
    def clear_all(self):
        self.records = []
        self._save()
        print("[HISTORY] All records cleared")
