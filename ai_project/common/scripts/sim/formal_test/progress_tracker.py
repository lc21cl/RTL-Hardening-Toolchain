#!/usr/bin/env python3
"""
progress_tracker.py — 长任务进度跟踪与状态管理

提供:
  - ProgressTracker: 单任务进度条 + ETA
  - BatchProgress: 批量处理进度
  - StageProgress: 多阶段任务进度

用法:
    from progress_tracker import ProgressTracker, BatchProgress

    # 简单进度条
    tracker = ProgressTracker(total=100, desc="Training")
    for i in range(100):
        do_work()
        tracker.update()

    # 批量进度
    bp = BatchProgress(files, desc="Inference")
    for f in bp:
        process(f)

    # 多阶段
    sp = StageProgress(stages=["Load", "Convert", "Infer"])
    sp.start("Load")
    ...
    sp.next()
"""

import time
import math
import sys
from typing import *
from collections import OrderedDict


def _terminal_width() -> int:
    """Get terminal width for progress bar sizing."""
    try:
        import shutil
        return shutil.get_terminal_size((80, 20)).columns
    except Exception:
        return 80


def _format_time(seconds: float) -> str:
    """Format seconds into human-readable time string."""
    if seconds < 0:
        return "--:--:--"
    h, remainder = divmod(int(seconds), 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _format_rate(rate: float) -> str:
    """Format rate (items/sec) into human-readable string."""
    if rate >= 1.0:
        return f"{rate:.2f} it/s"
    elif rate > 0:
        return f"{1.0/rate:.2f} s/it"
    return "-- it/s"


# ============================================================================
# ProgressTracker
# ============================================================================

class ProgressTracker:
    """Single-task progress tracker with visual progress bar and ETA.

    Args:
        total: Total number of items
        desc: Description text for the progress bar
        unit: Unit name for items (e.g., 'files', 'epochs')
        bar_length: Length of the progress bar in characters
        min_interval: Minimum interval between updates (seconds)
        dynamic_ncols: Auto-adjust to terminal width

    Usage:
        tracker = ProgressTracker(100, desc="Processing")
        for i in range(100):
            do_work()
            tracker.update()
        tracker.done()
    """

    def __init__(
        self,
        total: int,
        desc: str = "Processing",
        unit: str = "it",
        bar_length: int = 30,
        min_interval: float = 0.1,
        dynamic_ncols: bool = True,
    ):
        self.total = total
        self.desc = desc
        self.unit = unit
        self.bar_length = bar_length
        self.min_interval = min_interval
        self.dynamic_ncols = dynamic_ncols

        self.current = 0
        self.start_time = time.time()
        self._last_update = 0.0
        self._finished = False
        self._displayed = False

    def _get_bar_length(self) -> int:
        """Get dynamic bar length based on terminal width."""
        if not self.dynamic_ncols:
            return self.bar_length
        tw = _terminal_width()
        # Reserve space for: desc, percentage, counter, ETA, borders
        reserved = len(self.desc) + 20 + len(f"  {_format_time(0)}")
        return max(10, min(self.bar_length, tw - reserved))

    def update(self, n: int = 1):
        """Advance progress by n items and redisplay."""
        self.current += n
        now = time.time()
        if now - self._last_update < self.min_interval and self.current < self.total:
            return
        self._last_update = now
        self._display()

    def set(self, value: int):
        """Set current progress to an absolute value."""
        self.current = min(value, self.total)
        self._display()

    def _display(self):
        """Render the progress bar to stderr."""
        self._displayed = True
        bar_len = self._get_bar_length()
        fraction = self.current / max(self.total, 1)
        filled = int(bar_len * fraction)
        bar = '█' * filled + '░' * (bar_len - filled)
        pct = fraction * 100

        elapsed = time.time() - self.start_time
        rate = self.current / elapsed if elapsed > 0 else 0
        remaining = (self.total - self.current) / rate if rate > 0 else 0

        line = (
            f"\r  {self.desc}: |{bar}| "
            f"{pct:5.1f}% "
            f"[{self.current}/{self.total}, "
            f"{_format_rate(rate)}, "
            f"ETA {_format_time(remaining)}]"
        )
        sys.stderr.write(line)
        sys.stderr.flush()

        if self.current >= self.total:
            self.done()

    def reset(self, total: Optional[int] = None):
        """Reset tracker for reuse with optional new total."""
        if total is not None:
            self.total = total
        self.current = 0
        self.start_time = time.time()
        self._last_update = 0.0
        self._finished = False

    def done(self):
        """Mark progress as complete and print final line."""
        if self._finished:
            return
        self._finished = True
        self.current = self.total

        bar_len = self._get_bar_length()
        bar = '█' * bar_len
        elapsed = time.time() - self.start_time
        rate = self.total / elapsed if elapsed > 0 else 0

        sys.stderr.write(
            f"\r  {self.desc}: |{bar}| "
            f"100.0% "
            f"[{self.total}/{self.total}, "
            f"{_format_rate(rate)}, "
            f"{_format_time(elapsed)}]\n"
        )
        sys.stderr.flush()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.done()


# ============================================================================
# BatchProgress
# ============================================================================

class BatchProgress:
    """Progress tracker for batch processing of iterable items.

    Wraps an iterable and displays progress as items are consumed.

    Usage:
        bp = BatchProgress(file_list, desc="Processing")
        for item, idx, total in bp:
            process(item)

    Or:
        for item in bp.iterate():
            process(item)
    """

    def __init__(
        self,
        items: Sequence,
        desc: str = "Batch",
        unit: str = "items",
        bar_length: int = 30,
    ):
        self.items = list(items)
        self.total = len(self.items)
        self._tracker = ProgressTracker(
            self.total, desc=desc, unit=unit, bar_length=bar_length,
        )
        self._idx = 0

    def __iter__(self):
        self._idx = 0
        self._tracker.reset()
        return self

    def __next__(self):
        if self._idx >= self.total:
            self._tracker.done()
            raise StopIteration
        item = self.items[self._idx]
        self._idx += 1
        self._tracker.update()
        return (item, self._idx, self.total)

    def __len__(self):
        return self.total

    def iterate(self):
        """Simple iteration yielding just items."""
        self._idx = 0
        self._tracker.reset()
        for item in self.items:
            yield item
            self._idx += 1
            self._tracker.update()
        self._tracker.done()


# ============================================================================
# StageProgress
# ============================================================================

class StageProgress:
    """Multi-stage task progress tracker.

    Usage:
        sp = StageProgress(["Load Data", "Convert", "Train", "Evaluate"])
        sp.start("Load Data")
        ...  # show sub-progress with update()
        sp.next()
        sp.start("Train")
        ...  # per-epoch progress
        sp.next()
        sp.finish()
    """

    def __init__(self, stages: List[str], desc: str = "Pipeline"):
        self.stages = OrderedDict((s, {
            'status': 'pending',
            'start_time': None,
            'end_time': None,
        }) for s in stages)
        self.desc = desc
        self.current_stage = None
        self.current_tracker = None
        self.start_time = time.time()

    def start(self, stage: str, total: int = 0, **kwargs):
        """Start a stage with optional sub-progress tracking."""
        if stage not in self.stages:
            raise ValueError(f"Unknown stage: {stage}. Stages: {list(self.stages.keys())}")

        self.current_stage = stage
        self.stages[stage]['status'] = 'in_progress'
        self.stages[stage]['start_time'] = time.time()

        if total > 0:
            self.current_tracker = ProgressTracker(
                total, desc=f"  {stage}", **kwargs
            )
        else:
            # Print stage header without sub-progress
            stage_num = list(self.stages.keys()).index(stage) + 1
            print(f"\n  [{stage_num}/{len(self.stages)}] {stage}...")
            self.current_tracker = None

    def update(self, n: int = 1):
        """Update sub-progress of current stage."""
        if self.current_tracker:
            self.current_tracker.update(n)

    def next(self):
        """Mark current stage complete and print summary."""
        if self.current_stage is None:
            return

        stage = self.current_stage
        self.stages[stage]['status'] = 'completed'
        self.stages[stage]['end_time'] = time.time()
        elapsed = self.stages[stage]['end_time'] - self.stages[stage]['start_time']

        if self.current_tracker:
            self.current_tracker.done()
            self.current_tracker = None

        stage_num = list(self.stages.keys()).index(stage) + 1
        total_stages = len(self.stages)
        print(f"    [{stage_num}/{total_stages}] Done in {elapsed:.1f}s")

    def skip(self, stage: str):
        """Skip a stage (mark as skipped)."""
        if stage in self.stages:
            self.stages[stage]['status'] = 'skipped'

    def finish(self):
        """Finish all stages and print overall summary."""
        # Complete any remaining stage
        if self.current_stage and self.stages[self.current_stage]['status'] == 'in_progress':
            self.next()

        total_elapsed = time.time() - self.start_time
        completed = sum(1 for s in self.stages.values() if s['status'] == 'completed')
        skipped = sum(1 for s in self.stages.values() if s['status'] == 'skipped')

        print(f"\n{'=' * 62}")
        print(f"  {self.desc} Complete")
        print(f"{'=' * 62}")
        for i, (stage, info) in enumerate(self.stages.items(), 1):
            status = info['status']
            elapsed = ""
            if info['start_time'] and info['end_time']:
                elapsed = f" ({info['end_time'] - info['start_time']:.1f}s)"
            symbols = {'completed': '✅', 'in_progress': '⏳', 'pending': '  ', 'skipped': '⏭'}
            print(f"  {symbols.get(status, '  ')} Stage {i}: {stage}{elapsed}")
        print(f"\n  Total: {total_elapsed:.1f}s ({completed} completed, {skipped} skipped)")
        print(f"{'=' * 62}")
