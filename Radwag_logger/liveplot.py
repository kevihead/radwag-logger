#!/usr/bin/env python3
"""
Live EDF tail + plot for Sensirion-style .edf logs.

- Auto-detect newest .edf file in folder
- Incrementally reads appended lines (tail -f behavior)
- Parses numeric rows after the header
- Live plots Flow (slm), Pressure (Pa), Temperature (°C) vs time

Tested with the format shown in the prompt.
"""

from __future__ import annotations

import os
import time
import glob
from collections import deque
from dataclasses import dataclass
from typing import Optional, Tuple, List

import matplotlib.pyplot as plt


# ---------------------------- Config ----------------------------

LOG_DIR = r"C:\Users\Alex\data_logging"   # <-- change me
POLL_SEC = 0.25                          # how often to poll for new data
SWITCH_CHECK_SEC = 2.0                   # how often to check for a newer .edf file
MAX_POINTS = 60_000                      # keep last N points in memory (e.g., 60k ~= 60s at 1kHz)

# If your data is 1000 Hz, plotting every point can be heavy.
# You can decimate the plotted points without losing parsing.
PLOT_DECIMATE = 5                        # plot every Nth point (1 = plot all)


# ---------------------------- Helpers ----------------------------

def newest_file_in_dir(folder: str, pattern: str = "*.edf") -> Optional[str]:
    files = glob.glob(os.path.join(folder, pattern))
    if not files:
        return None
    return max(files, key=lambda p: os.path.getmtime(p))


@dataclass
class EdfTailReader:
    path: str
    _fh: Optional[object] = None
    _pos: int = 0
    _ready_for_data: bool = False  # set True after we pass column header line

    def open(self) -> None:
        self.close()
        # open with universal newlines; errors ignored in case of odd chars like °C
        self._fh = open(self.path, "r", encoding="utf-8", errors="replace", newline=None)
        self._pos = 0
        self._ready_for_data = False

    def close(self) -> None:
        if self._fh:
            try:
                self._fh.close()
            except Exception:
                pass
        self._fh = None

    def _ensure_open(self) -> None:
        if self._fh is None:
            self.open()

    def read_new_rows(self) -> List[Tuple[float, float, float, float]]:
        """
        Returns newly appended data rows as list of tuples:
        (epoch_utc, flow, pressure, temperature)
        """
        self._ensure_open()
        assert self._fh is not None

        # Seek to last position and read whatever is new
        self._fh.seek(self._pos, os.SEEK_SET)
        chunk = self._fh.read()
        self._pos = self._fh.tell()

        if not chunk:
            return []

        rows: List[Tuple[float, float, float, float]] = []
        for line in chunk.splitlines():
            line = line.strip()
            if not line:
                continue

            # skip metadata lines
            if line.startswith("EdfVersion=") or line.startswith("#"):
                continue

            # Detect the column header line
            # Example: Epoch_UTC  F_...  P_...  T_...
            if (not self._ready_for_data) and line.startswith("Epoch_UTC"):
                self._ready_for_data = True
                continue

            if not self._ready_for_data:
                continue  # still in preamble

            # Now we expect numeric data rows with 4 tab-separated fields
            # Example: 1771475502.906256   0.033333   19.836728   28.760000
            parts = line.split()
            if len(parts) < 4:
                continue

            try:
                epoch = float(parts[0])
                flow = float(parts[1])
                pres = float(parts[2])
                temp = float(parts[3])
                rows.append((epoch, flow, pres, temp))
            except ValueError:
                # ignore malformed rows
                continue

        return rows


# ---------------------------- Main live plot ----------------------------

def main() -> None:
    plt.ion()

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, sharex=True)
    fig.canvas.manager.set_window_title("EDF Live Plot")

    ax1.set_ylabel("Flow (slm)")
    ax2.set_ylabel("Pressure (Pa)")
    ax3.set_ylabel("Temp (°C)")
    ax3.set_xlabel("Time (s) relative")

    # buffers
    t_buf = deque(maxlen=MAX_POINTS)
    f_buf = deque(maxlen=MAX_POINTS)
    p_buf = deque(maxlen=MAX_POINTS)
    T_buf = deque(maxlen=MAX_POINTS)

    line1, = ax1.plot([], [], lw=1)
    line2, = ax2.plot([], [], lw=1)
    line3, = ax3.plot([], [], lw=1)

    current_path = newest_file_in_dir(LOG_DIR)
    if current_path is None:
        raise FileNotFoundError(f"No .edf files found in: {LOG_DIR}")

    reader = EdfTailReader(current_path)
    reader.open()
    print(f"[info] Tailing: {current_path}")

    last_switch_check = 0.0
    t0: Optional[float] = None

    while True:
        now = time.time()

        # Periodically check if a newer file appeared
        if now - last_switch_check > SWITCH_CHECK_SEC:
            last_switch_check = now
            newest = newest_file_in_dir(LOG_DIR)
            if newest and os.path.abspath(newest) != os.path.abspath(current_path):
                current_path = newest
                reader = EdfTailReader(current_path)
                reader.open()
                t0 = None
                t_buf.clear(); f_buf.clear(); p_buf.clear(); T_buf.clear()
                print(f"[info] Switched to newest file: {current_path}")

        new_rows = reader.read_new_rows()
        if new_rows:
            for epoch, flow, pres, temp in new_rows:
                if t0 is None:
                    t0 = epoch
                t_rel = epoch - t0
                t_buf.append(t_rel)
                f_buf.append(flow)
                p_buf.append(pres)
                T_buf.append(temp)

            # decimate for plotting speed
            if PLOT_DECIMATE > 1 and len(t_buf) > PLOT_DECIMATE:
                t_plot = list(t_buf)[::PLOT_DECIMATE]
                f_plot = list(f_buf)[::PLOT_DECIMATE]
                p_plot = list(p_buf)[::PLOT_DECIMATE]
                T_plot = list(T_buf)[::PLOT_DECIMATE]
            else:
                t_plot = list(t_buf)
                f_plot = list(f_buf)
                p_plot = list(p_buf)
                T_plot = list(T_buf)

            line1.set_data(t_plot, f_plot)
            line2.set_data(t_plot, p_plot)
            line3.set_data(t_plot, T_plot)

            # autoscale
            for ax in (ax1, ax2, ax3):
                ax.relim()
                ax.autoscale_view()

            ax1.set_title(os.path.basename(current_path))
            fig.tight_layout()
            fig.canvas.draw()
            fig.canvas.flush_events()

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
