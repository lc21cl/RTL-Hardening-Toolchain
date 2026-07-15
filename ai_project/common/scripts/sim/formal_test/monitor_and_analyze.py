import os
import re
import time
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
LOG_FILE = Path(os.environ.get(
    'TRAIN_LOG',
    r'C:\Users\86156\AppData\Local\Temp\trae-agent-toolhost\jobs\job-07f6f608ef7b410fbdc2ef54919fc70b\output.log'))
MODEL_DIR = SCRIPT_DIR / 'data' / 'models'
DATA_PATH = SCRIPT_DIR / 'data' / 'training_data.pt'

TRIGGER_EPOCH = 50
POLL_INTERVAL = 120
BASELINE_PI_RECALL = 0.0
BASELINE_F1 = 0.9891

EPOCH_RE = re.compile(r'Epoch\s+(\d+)/\d+.*Best:\s+([\d.]+)\s+@(\d+)')
DONE_MARKERS = ['Traceback', 'Error:', 'saved to', 'Saved best model to']
TRAIN_COMPLETE_MARKERS = [
    r'Training complete.*seed',
    r'Best model saved.*seed',
    r'=\s*\n\s*Training seed=\d+\s*\n',
    r'Model saved.*local_seed',
    r'Test F1.*seed',
]

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f'[{ts}] {msg}', flush=True)

def tail_text(path, n=200):
    if not path.exists():
        return ''
    lines = path.read_text(encoding='utf-8', errors='ignore').splitlines()
    return '\n'.join(lines[-n:])

def parse_latest_epoch(text):
    matches = EPOCH_RE.findall(text)
    if not matches:
        return None, None, None
    last = matches[-1]
    return int(last[0]), float(last[1]), int(last[2])

def is_training_done(text):
    lower = text.lower()
    if 'traceback' in lower or 'error:' in lower:
        return True, 'error'

    for pattern in TRAIN_COMPLETE_MARKERS:
        if re.search(pattern, text, re.IGNORECASE):
            return True, 'done'

    if 'model saved to' in lower and 'local_seed' in lower:
        return True, 'done'

    epoch_matches = EPOCH_RE.findall(text)
    if epoch_matches:
        last_epoch = int(epoch_matches[-1][0])
        if last_epoch >= 200:
            return True, 'max_epochs'

    return False, ''

def run_error_analysis():
    log('--- Running Error Analysis ---')
    script = SCRIPT_DIR / 'error_analysis.py'
    if not script.exists():
        log(f'ERROR: {script} not found')
        return None

    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(SCRIPT_DIR),
            capture_output=True, text=True, timeout=300,
        )
        output = result.stdout + result.stderr
        print(output)

        pi_recall = extract_pi_recall(output)
        f1 = extract_f1(output)
        return {'pi_recall': pi_recall, 'f1': f1, 'output': output}
    except subprocess.TimeoutExpired:
        log('ERROR: error_analysis.py timed out')
        return None
    except Exception as e:
        log(f'ERROR: {e}')
        return None

def extract_pi_recall(text):
    m = re.search(r'PI\s+\d[\d,]*\s+\d+\s+\d+\s+(\d+)\s+\d+\s+0\.(\d+)', text)
    if m:
        return float(f'0.{m.group(2)}')
    m = re.search(r'PI.*?Recall[:\s]+([\d.]+)', text)
    if m:
        return float(m.group(1))
    return None

def extract_f1(text):
    m = re.search(r'F1[:\s]+([\d.]+)', text)
    if m:
        return float(m.group(1))
    return None

def compare_with_baseline(result):
    if not result or result['pi_recall'] is None:
        log('WARNING: Could not extract PI recall from results')
        return

    pi_recall = result['pi_recall']
    f1 = result.get('f1', 0)

    log('=' * 60)
    log('  PI Node Recall Comparison')
    log('=' * 60)
    log(f'  Baseline (10 features):  PI Recall = {BASELINE_PI_RECALL:.4f}, F1 = {BASELINE_F1:.4f}')
    log(f'  New model (12 features): PI Recall = {pi_recall:.4f}, F1 = {f1:.4f}')

    delta_recall = pi_recall - BASELINE_PI_RECALL
    delta_f1 = (f1 - BASELINE_F1) if f1 else 0

    log(f'  Delta: PI Recall {delta_recall:+.4f}, F1 {delta_f1:+.4f}')

    if delta_recall > 0.1:
        log('  STATUS: SIGNIFICANT IMPROVEMENT in PI recall')
        log('  Recommendation: Continue training, then run ensemble')
    elif delta_recall > 0:
        log('  STATUS: MODEST IMPROVEMENT in PI recall')
        log('  Recommendation: Consider PI-specific classifier')
    else:
        log('  STATUS: NO IMPROVEMENT in PI recall')
        log('  Recommendation: Implement PI-specific classifier (see pi_classifier_pseudocode.py)')
    log('=' * 60)

def main():
    log('=' * 60)
    log('  Training Monitor — Auto Error Analysis Trigger')
    log('=' * 60)
    log(f'  Log file: {LOG_FILE}')
    log(f'  Trigger: epoch >= {TRIGGER_EPOCH} or training done')
    log(f'  Poll interval: {POLL_INTERVAL}s')
    log(f'  Baseline: PI Recall={BASELINE_PI_RECALL:.4f}, F1={BASELINE_F1:.4f}')

    triggered = False
    start_time = time.time()

    while True:
        text = tail_text(LOG_FILE, 300)

        if not text:
            log(f'Waiting for log file... (elapsed: {int(time.time()-start_time)}s)')
            time.sleep(POLL_INTERVAL)
            continue

        epoch, best_f1, best_epoch = parse_latest_epoch(text)
        done, reason = is_training_done(text)

        if epoch:
            log(f'Current: epoch={epoch}, best_val_f1={best_f1:.4f}@{best_epoch}')

        if not triggered and (epoch and epoch >= TRIGGER_EPOCH):
            log(f'Trigger condition met: epoch {epoch} >= {TRIGGER_EPOCH}')
            triggered = True
            result = run_error_analysis()
            if result:
                compare_with_baseline(result)

        if done:
            log(f'Training finished (reason: {reason})')
            if not triggered:
                log('Running final error analysis...')
                result = run_error_analysis()
                if result:
                    compare_with_baseline(result)
            break

        if time.time() - start_time > 3600 * 4:
            log('Timeout: 4 hours elapsed, stopping monitor')
            break

        time.sleep(POLL_INTERVAL)

    log('Monitor exited.')

if __name__ == '__main__':
    main()