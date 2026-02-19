"""
Integrated Radwag Scale + Sensirion Flow Logger
- Logs weight from Radwag scale via serial
- Logs flow from Sensirion Control Center (reads log files)
- Auto-starts Control Center measurement when logging begins
- Synchronized timestamps and CSV output
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import serial
import threading
import csv
import datetime
import os
import queue
import time
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.animation import FuncAnimation
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator
from collections import deque
from pathlib import Path
import subprocess

class ControlCenterFlowReader:
    """Read flow data from Sensirion Control Center log files"""

    def __init__(self):
        self.log_directory = None
        self.current_log_file = None
        self.last_position = 0
        self.last_flow_value = None
        self.last_pressure_value = None
        self.last_temperature_value = None
        self.last_timestamp = None
        self._ready_for_data = False  # Track if we've passed the column header

        # Track file growth (for "measurement active" detection)
        self._last_file_size = None
        self._last_file_mtime = None

    def set_log_directory(self, path: str | Path | None):
        if not path:
            self.log_directory = None
            return
        self.log_directory = Path(path)

    def reset_to_tail(self):
        """After Start Logging, ignore existing contents and only read newly appended data."""
        latest_file = self.find_latest_log_file()
        self.current_log_file = latest_file
        self._ready_for_data = False

        if not latest_file or not latest_file.exists():
            self.last_position = 0
            return

        try:
            with open(latest_file, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(0, os.SEEK_END)
                self.last_position = f.tell()
        except Exception:
            self.last_position = 0

    def get_latest_file_status(self):
        """Return (latest_file, size_bytes, mtime, grew_recently_bool)."""
        latest = self.find_latest_log_file()
        if not latest or not latest.exists():
            self._last_file_size = None
            self._last_file_mtime = None
            return None, None, None, False

        try:
            stat = latest.stat()
            size = stat.st_size
            mtime = stat.st_mtime
        except Exception:
            return latest, None, None, False

        grew = False
        if self._last_file_size is not None and size is not None:
            grew = size > self._last_file_size

        self._last_file_size = size
        self._last_file_mtime = mtime
        return latest, size, mtime, grew

    def find_log_directory(self):
        """Find Control Center log directory"""
        possible_paths = [
            Path("C:/Users/Alex/data_logging"),
            Path.home() / "AppData" / "Local" / "Sensirion" / "ControlCenter" / "Logs",
            Path.home() / "Documents" / "Sensirion" / "ControlCenter" / "Logs",
            Path.home() / "AppData" / "Roaming" / "Sensirion" / "ControlCenter" / "Logs",
            Path("C:/ProgramData/Sensirion/ControlCenter/Logs"),
            Path("C:/Users/Public/Documents/Sensirion/ControlCenter/Logs"),
        ]
        
        for path in possible_paths:
            if path.exists():
                return path
        return None
    
    def find_latest_log_file(self):
        """Find the most recently modified log file"""
        if not self.log_directory:
            self.log_directory = self.find_log_directory()
        
        if not self.log_directory or not self.log_directory.exists():
            return None
        
        log_files = list(self.log_directory.glob("*.edf")) + list(self.log_directory.glob("*.csv")) + list(self.log_directory.glob("*.txt"))
        
        if not log_files:
            return None
        
        latest_file = max(log_files, key=lambda f: f.stat().st_mtime)
        return latest_file
    
    def read_new_data(self):
        """Read new data from log file since last read"""
        latest_file = self.find_latest_log_file()
        
        if not latest_file:
            return None
        
        # Reset position if new file
        if self.current_log_file != latest_file:
            self.current_log_file = latest_file
            self.last_position = 0
            self._ready_for_data = False  # Reset for new file
        
        new_data = []
        
        try:
            with open(self.current_log_file, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(self.last_position)
                new_lines = f.readlines()
                self.last_position = f.tell()
                
                for line in new_lines:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    # Detect column header line (starts with "Epoch_UTC")
                    if (not self._ready_for_data) and line.startswith('Epoch_UTC'):
                        self._ready_for_data = True
                        continue
                    
                    if not self._ready_for_data:
                        continue  # Still in header/metadata section
                    
                    # Parse space-delimited EDF format
                    # Format: Epoch_UTC Flow(slm) Pressure(Pa) Temperature(°C)
                    parts = line.split()
                    
                    if len(parts) >= 4:
                        try:
                            epoch = float(parts[0])  # Epoch timestamp
                            flow_slm = float(parts[1])  # Flow in slm
                            pressure_pa = float(parts[2])  # Pressure in Pa
                            temperature_c = float(parts[3])  # Temperature in °C

                            # Convert epoch to datetime
                            from datetime import datetime
                            timestamp = datetime.fromtimestamp(epoch).isoformat()

                            new_data.append({
                                'epoch': epoch,
                                'timestamp': timestamp,
                                'flow_slm': flow_slm,
                                'pressure_pa': pressure_pa,
                                'temperature_c': temperature_c
                            })

                            self.last_flow_value = flow_slm
                            self.last_pressure_value = pressure_pa
                            self.last_temperature_value = temperature_c
                            self.last_timestamp = timestamp
                        except (ValueError, IndexError):
                            continue

        except Exception as e:
            return None
        
        return new_data if new_data else None
    
    def get_latest_flow(self):
        """Get most recent flow value (in slm)"""
        new_data = self.read_new_data()
        
        if new_data:
            return new_data[-1]['flow_slm']
        
        return self.last_flow_value

    def reset_for_new_session(self, start_epoch: float | None = None):
        """Prepare to attach to a (possibly already-growing) log file.

        We intentionally do NOT seek to end-of-file, because Control Center might already
        be measuring and we may need to scan forward to the header (Epoch_UTC) to start parsing.

        The caller can provide start_epoch to allow the UI thread to filter out older samples.
        """
        latest_file = self.find_latest_log_file()
        self.current_log_file = latest_file
        self._ready_for_data = False
        self.last_position = 0
        # Note: start_epoch is stored by ScaleFlowLogger for filtering; reader stays generic.


class ScaleFlowLogger:
    def __init__(self, root):
        self.root = root
        self.root.title("Radwag Scale + Sensirion Flow Logger")
        self.root.geometry("1400x900")
        
        # Serial connection for scale
        self.scale_com_port = "COM11"
        self.scale_baud_rate = 9600
        self.scale_serial_connection = None
        
        # Flow reader
        self.flow_reader = ControlCenterFlowReader()
        self.control_center_running = False
        
        # Logging variables
        self.is_logging = False
        self.log_file = None
        self.csv_writer = None
        self.start_time = None
        self.record_count = 0
        
        # Threading and queues
        self.scale_data_queue = queue.Queue()
        self.flow_data_queue = queue.Queue()
        self.scale_read_thread = None
        self.flow_read_thread = None
        self.stop_reading = False
        
        # Graph data storage
        self.graph_timestamps = deque(maxlen=1000)
        self.graph_scale_readings = deque(maxlen=1000)
        self.graph_flow_readings = deque(maxlen=1000)
        self.graph_start_time = None
        
        # Flow log/plot rates
        self.flow_log_hz = 10.0
        self.flow_plot_hz = 10.0

        # Internals
        self.last_scale_reading = None
        self.last_scale_stability = None
        self.flow_output_hz = self.flow_log_hz  # kept for backward-compat; used by flow_bin_seconds
        self.flow_bin_seconds = 1.0 / self.flow_output_hz

        # Plot decimation: only add a plotted point every N logged bins
        self._flow_plot_every_n = max(1, int(round(self.flow_log_hz / self.flow_plot_hz)))
        self._flow_logged_bins_since_plot = 0

        # Batch flushing (reduce disk overhead)
        self.csv_flush_interval_s = 1.0
        self._last_csv_flush_ts = time.time()

        # Throttle UI queue processing so a big EDF flush can't freeze Tk
        self.max_flow_items_per_ui_tick = 500
        
        # Flow log folder (user selectable)
        self.flow_log_dir_var = tk.StringVar(value=str(Path("C:/Users/Alex/data_logging")))

        # Track whether Control Center is actively writing (heuristic: latest EDF grows)
        self.flow_measurement_active = False

        # Debounced measurement detection: check file growth over a longer window
        self.flow_status_check_interval_ms = 5000
        self._flow_last_status_size = None
        self._flow_last_status_path = None

        # Setup GUI
        self.setup_gui()
        self.setup_graph()
        
        # Start checking for data and Control Center
        self.check_data_queue()
        self.check_control_center_status()
        
    def check_control_center_status(self):
        """Periodically check if Control Center is running and if measurement is active."""
        try:
            import pygetwindow as gw

            window_titles = ['ControlCenter', 'Control Center', 'Sensirion Control Center']

            found = False
            for title in window_titles:
                windows = gw.getWindowsWithTitle(title)
                if windows:
                    found = True
                    break

            self.control_center_running = found
        except ImportError:
            # If pygetwindow isn't installed, we still can track activity via file growth
            self.control_center_running = False
        except Exception:
            pass

        # File growth monitoring (works regardless of pygetwindow)
        self.flow_reader.set_log_directory(self.flow_log_dir_var.get())
        latest, size, mtime, _grew_since_last_poll = self.flow_reader.get_latest_file_status()

        # Debounce: only decide "measuring" based on whether size increased over the last 5s window
        grew_over_window = False
        if latest is not None and size is not None:
            # If file changed (new latest file), reset baseline for the next window
            if self._flow_last_status_path != latest:
                self._flow_last_status_path = latest
                self._flow_last_status_size = size
                grew_over_window = False
            else:
                if self._flow_last_status_size is not None and size > self._flow_last_status_size:
                    grew_over_window = True
                # Update baseline for next interval
                self._flow_last_status_size = size

        self.flow_measurement_active = bool(grew_over_window)

        if latest is None:
            self.flow_status_var.set("Flow: No log files found")
        else:
            name = latest.name
            if self.flow_measurement_active:
                self.flow_status_var.set(f"Flow: Measuring ✓ ({name})")
            else:
                self.flow_status_var.set(f"Flow: Not measuring ({name})")

        # Check again every 5 seconds
        self.root.after(self.flow_status_check_interval_ms, self.check_control_center_status)

    def setup_gui(self):
        # Main paned window
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left frame
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=1)
        
        # Right frame for graph
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=2)
        
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(2, weight=1)
        
        # Connection settings
        settings_frame = ttk.LabelFrame(left_frame, text="Connection Settings", padding="5")
        settings_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        settings_frame.columnconfigure(1, weight=1)
        
        # Scale connection
        ttk.Label(settings_frame, text="Scale COM:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.scale_com_port_var = tk.StringVar(value=self.scale_com_port)
        ttk.Entry(settings_frame, textvariable=self.scale_com_port_var, width=8).grid(row=0, column=1, sticky=tk.W, padx=(0, 10))
        
        ttk.Label(settings_frame, text="Baud:").grid(row=0, column=2, sticky=tk.W)
        self.scale_baud_rate_var = tk.StringVar(value=str(self.scale_baud_rate))
        ttk.Entry(settings_frame, textvariable=self.scale_baud_rate_var, width=8).grid(row=0, column=3, sticky=tk.W, padx=(5, 10))
        
        self.scale_status_var = tk.StringVar(value="Scale: Disconnected")
        scale_status_label = ttk.Label(settings_frame, textvariable=self.scale_status_var, font=('Arial', 9, 'bold'))
        scale_status_label.grid(row=0, column=4, sticky=tk.W, padx=(10, 0))
        
        # Flow status (single label, like before)
        self.flow_status_var = tk.StringVar(value="Flow: Not measuring")
        flow_status_label = ttk.Label(settings_frame, textvariable=self.flow_status_var, font=('Arial', 9, 'bold'))
        flow_status_label.grid(row=1, column=0, columnspan=5, sticky=tk.W, padx=(0, 5), pady=(5, 0))

        # Flow log folder selection row
        ttk.Label(settings_frame, text="Flow Logs Folder:").grid(row=2, column=0, sticky=tk.W, padx=(0, 5), pady=(5, 0))
        ttk.Entry(settings_frame, textvariable=self.flow_log_dir_var).grid(row=2, column=1, columnspan=3, sticky=(tk.W, tk.E), pady=(5, 0))
        self.browse_flow_folder_btn = ttk.Button(settings_frame, text="Browse...", command=self.browse_flow_folder)
        self.browse_flow_folder_btn.grid(row=2, column=4, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # Control buttons
        button_frame = ttk.Frame(left_frame)
        button_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        self.connect_scale_btn = ttk.Button(button_frame, text="Connect Scale", command=self.connect_scale)
        self.connect_scale_btn.pack(side=tk.LEFT, padx=(0, 5), anchor='w')

        self.start_btn = ttk.Button(button_frame, text="Start Logging", command=self.start_logging)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 5), anchor='w')

        self.stop_btn = ttk.Button(button_frame, text="Stop Logging", command=self.stop_logging, state='disabled')
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 5), anchor='w')

        self.reset_btn = ttk.Button(button_frame, text="Reset", command=self.reset_logging)
        self.reset_btn.pack(side=tk.LEFT, anchor='w')
        
        # Data display
        data_frame = ttk.LabelFrame(left_frame, text="Live Data", padding="5")
        data_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        data_frame.columnconfigure(0, weight=1)
        data_frame.rowconfigure(1, weight=1)
        
        # Current readings
        current_frame = ttk.Frame(data_frame)
        current_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        current_frame.columnconfigure(1, weight=1)
        
        ttk.Label(current_frame, text="Scale:", font=('Arial', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.current_scale_reading_var = tk.StringVar(value="No data")
        ttk.Label(current_frame, textvariable=self.current_scale_reading_var, 
                 font=('Arial', 12, 'bold'), foreground='blue').grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(current_frame, text="Flow:", font=('Arial', 10, 'bold')).grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=(5, 0))
        self.current_flow_reading_var = tk.StringVar(value="No data")
        ttk.Label(current_frame, textvariable=self.current_flow_reading_var, 
                 font=('Arial', 12, 'bold'), foreground='green').grid(row=1, column=1, sticky=tk.W, pady=(5, 0))
        
        ttk.Label(current_frame, text="Pressure:", font=('Arial', 10, 'bold')).grid(row=2, column=0, sticky=tk.W, padx=(0, 5), pady=(5, 0))
        self.current_pressure_reading_var = tk.StringVar(value="No data")
        ttk.Label(current_frame, textvariable=self.current_pressure_reading_var, 
                 font=('Arial', 12, 'bold'), foreground='orange').grid(row=2, column=1, sticky=tk.W, pady=(5, 0))
        
        ttk.Label(current_frame, text="Temperature:", font=('Arial', 10, 'bold')).grid(row=3, column=0, sticky=tk.W, padx=(0, 5), pady=(5, 0))
        self.current_temperature_reading_var = tk.StringVar(value="No data")
        ttk.Label(current_frame, textvariable=self.current_temperature_reading_var, 
                 font=('Arial', 12, 'bold'), foreground='red').grid(row=3, column=1, sticky=tk.W, pady=(5, 0))
        
        # Log display
        self.log_display = scrolledtext.ScrolledText(data_frame, height=10, width=50)
        self.log_display.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Log info
        info_frame = ttk.Frame(left_frame)
        info_frame.grid(row=3, column=0, sticky=(tk.W, tk.E))
        
        log_status_frame = ttk.Frame(info_frame)
        log_status_frame.pack(side=tk.LEFT)
        
        self.log_status_indicator = tk.Label(log_status_frame, text="●", font=('Arial', 20), fg='red')
        self.log_status_indicator.pack(side=tk.LEFT, padx=(0, 5), anchor='center')
        
        self.log_info_var = tk.StringVar(value="No active log file")
        ttk.Label(log_status_frame, textvariable=self.log_info_var, font=('Arial', 12)).pack(side=tk.LEFT, anchor='center')
        
        self.record_count_var = tk.StringVar(value="Records: 0")
        ttk.Label(info_frame, textvariable=self.record_count_var, font=('Arial', 10)).pack(side=tk.RIGHT)
        
        self.graph_frame = right_frame
    
    def browse_flow_folder(self):
        """Pick folder where Control Center writes EDF logs."""
        from tkinter import filedialog
        folder = filedialog.askdirectory(initialdir=self.flow_log_dir_var.get() or os.getcwd())
        if folder:
            self.flow_log_dir_var.set(folder)
            self.flow_reader.set_log_directory(folder)

    def setup_graph(self):
        """Setup matplotlib graph with stacked axes (flow above weight)."""
        plt.style.use('default')

        self.fig, (self.ax_flow, self.ax_weight) = plt.subplots(
            2,
            1,
            figsize=(8, 6),
            sharex=True,
            gridspec_kw={'height_ratios': [1, 1]}
        )
        self.fig.patch.set_facecolor('white')

        # Flow plot (top)
        self.ax_flow.set_ylabel('Flow Rate (slm)', color='green')
        self.ax_flow.grid(True, alpha=0.3)
        self.ax_flow.set_ylim(0, 50)
        self.flow_line, = self.ax_flow.plot([], [], 'g-', linewidth=1.5, label='Flow Rate')

        # Weight plot (bottom)
        self.ax_weight.set_xlabel('Time (seconds)')
        self.ax_weight.set_ylabel('Weight (g)', color='blue')
        self.ax_weight.grid(True, alpha=0.3)
        self.scale_line, = self.ax_weight.plot([], [], 'b-', linewidth=1.5, label='Weight')

        # Embed in tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.graph_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Start animation
        self.ani = FuncAnimation(self.fig, self.update_graph, interval=200, blit=False, cache_frame_data=False)
    
    def parse_scale_data(self, raw_data):
        """Parse the scale data to extract stability and reading"""
        try:
            # Example: "SI ?       0.00 g" or "SI ? -     0.02 g"
            # Remove "SI" and extra spaces
            data = raw_data.strip()
            
            # Check if stable (no ?) or unstable (has ?)
            stable = 0 if '?' in data else 1
            
            # Extract the numeric value
            # Remove SI, ?, and g, then clean up spaces
            cleaned = data.replace('SI', '').replace('?', '').replace('g', '').strip()
            
            # Handle the minus sign that might be separated
            if '-' in cleaned:
                # Find the minus and the number
                parts = cleaned.split()
                reading = -float([p for p in parts if p.replace('.', '').replace('-', '').isdigit()][-1])
            else:
                # Extract just the number
                parts = cleaned.split()
                reading = float([p for p in parts if p.replace('.', '').isdigit()][-1])
                
            return stable, reading
            
        except (ValueError, IndexError) as e:
            return None, None

    def connect_scale(self):
        """Connect to Radwag scale"""
        try:
            port = self.scale_com_port_var.get()
            baud = int(self.scale_baud_rate_var.get())
            
            self.scale_serial_connection = serial.Serial(
                port=port,
                baudrate=baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            time.sleep(0.5)
            
            self.scale_status_var.set(f"Scale: Connected ({port})")
            self.log_message(f"Scale connected on {port}")
            
            self.connect_scale_btn.config(state='disabled')
            
            # Start reading thread
            self.stop_reading = False
            self.scale_read_thread = threading.Thread(target=self.read_scale_data, daemon=True)
            self.scale_read_thread.start()
            
        except Exception as e:
            messagebox.showerror("Connection Error", f"Could not connect to scale:\n{e}")
            self.scale_status_var.set("Scale: Connection Failed")
    
    def start_logging(self):
        """Start logging both scale and flow data"""
        try:
            self.log_message("Start Logging pressed")

            # Ensure flow reader uses selected folder
            self.flow_reader.set_log_directory(self.flow_log_dir_var.get())

            # Mark the logger start time for filtering (Control Center may already be measuring)
            self._logging_start_epoch = time.time()

            # Reset flow reader state but do not tail-to-EOF (so we can attach to an already-running measurement)
            self.flow_reader.reset_for_new_session(start_epoch=self._logging_start_epoch)

            # Reset flow bin state so the first new data starts bins cleanly
            self._flow_bin_start_epoch = None
            self._flow_epoch_zero = None
            self._flow_bin_sum = 0.0
            self._flow_bin_count = 0
            self._flow_bin_pressure_sum = 0.0
            self._flow_bin_temp_sum = 0.0

            # Create log file
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"scale_flow_log_{timestamp}.csv"
            log_path = Path(__file__).parent / "data" / log_filename
            log_path.parent.mkdir(exist_ok=True)
            
            self.log_file = open(log_path, 'w', newline='')
            self.csv_writer = csv.writer(self.log_file)
            self.csv_writer.writerow([
                'Timestamp',
                'UnixTime_s',
                'Elapsed_Time_s',
                'Weight_g',
                'Flow_slm',
                'Pressure_Pa',
                'Temperature_C',
                'Stability'
            ])
            
            self.is_logging = True
            self.start_time = datetime.datetime.now()
            self.graph_start_time = time.time()
            self.record_count = 0
            
            # Update UI
            self.log_status_indicator.config(fg='green')
            self.log_info_var.set(f"Logging: {log_filename}")
            self.start_btn.config(state='disabled')
            self.stop_btn.config(state='normal')
            
            self.log_message(f"Started logging to {log_filename}")
            
            # Start Control Center measurement if available
            if self.control_center_running:
                self.log_message("Starting Control Center measurement...")
                self.root.after(500, self.trigger_control_center_start)
            
            # Start flow reading thread
            if not (self.flow_read_thread and self.flow_read_thread.is_alive()):
                self.flow_read_thread = threading.Thread(target=self.read_flow_data, daemon=True)
                self.flow_read_thread.start()
            
        except Exception as e:
            messagebox.showerror("Logging Error", f"Could not start logging:\n{e}")
            self.is_logging = False
    
    def trigger_control_center_start(self):
        """Remind user to start Control Center measurement manually"""
        self.log_message("Please start measurement in Control Center manually")
        self.flow_status_var.set("Flow: Start manually in Control Center")
    
    def stop_logging(self):
        """Stop logging"""
        self.is_logging = False
        
        if self.log_file:
            self.log_file.close()
            self.log_file = None
        
        # Stop Control Center measurement
        if self.control_center_running:
            self.log_message("Please stop Control Center measurement manually")
        
        self.log_status_indicator.config(fg='red')
        self.log_info_var.set("Logging stopped")
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        
        self.log_message(f"Stopped logging. Total records: {self.record_count}")
    
    def reset_logging(self):
        """Reset the logger"""
        if self.is_logging:
            self.stop_logging()

        # Clear graph data
        self.graph_timestamps.clear()
        self.graph_scale_readings.clear()
        self.graph_flow_readings.clear()

        # Reset counters
        self.record_count = 0
        self.record_count_var.set("Records: 0")

        # Clear display
        self.log_display.delete(1.0, tk.END)
        self.current_scale_reading_var.set("No data")
        self.current_flow_reading_var.set("No data")
        self.current_pressure_reading_var.set("No data")
        self.current_temperature_reading_var.set("No data")

        # Immediately reset plot visuals
        try:
            self.flow_line.set_data([], [])
            self.scale_line.set_data([], [])

            # Restore default view
            self.ax_flow.set_ylim(0, 50)
            self.ax_flow.set_xlim(0, 1)

            self.ax_weight.relim()
            self.ax_weight.autoscale_view()
            self.canvas.draw_idle()
        except Exception:
            pass

        self.log_message("Logger reset")
    
    def read_scale_data(self):
        """Thread function to read scale data"""
        while not self.stop_reading:
            try:
                if self.scale_serial_connection and self.scale_serial_connection.is_open:
                    if self.scale_serial_connection.in_waiting > 0:
                        line = self.scale_serial_connection.readline().decode('utf-8', errors='ignore').strip()
                        
                        if line:
                            self.scale_data_queue.put(line)
            except Exception as e:
                pass
            
            time.sleep(0.1)
    
    def read_flow_data(self):
        """Thread function to read flow data from Control Center logs"""
        self.log_message("Flow reader thread started")
        read_count = 0

        while not self.stop_reading and self.is_logging:
            try:
                new_data = self.flow_reader.read_new_data()

                if new_data:
                    for point in new_data:
                        # include epoch so main thread can bin correctly even when data arrives in bursts
                        self.flow_data_queue.put({
                            'epoch': point.get('epoch'),
                            'timestamp': point.get('timestamp'),
                            'flow_slm': point.get('flow_slm'),
                            'pressure_pa': point.get('pressure_pa'),
                            'temperature_c': point.get('temperature_c')
                        })
                        read_count += 1

                    latest = new_data[-1]
                    if read_count % 250 == 0:
                        self.log_message(
                            f"Flow batch received. Latest: {latest['flow_slm']:.6f} slm, "
                            f"P: {latest['pressure_pa']:.2f} Pa, T: {latest['temperature_c']:.2f}°C "
                            f"(total samples: {read_count})"
                        )
            except Exception as e:
                self.log_message(f"⚠ Flow reader error: {e}")

            time.sleep(0.5)

        self.log_message(f"Flow reader thread stopped (total samples: {read_count})")

    def check_data_queue(self):
        """Process data from queues"""
        # Process scale data
        while not self.scale_data_queue.empty():
            line = self.scale_data_queue.get()
            self.process_scale_data(line)

        # Process flow data (throttled)
        processed = 0
        latest_flow_value = None
        latest_pressure_value = None
        latest_temperature_value = None

        emitted_bins = 0
        max_bins_to_emit_per_tick = 50

        while (not self.flow_data_queue.empty()) and (processed < self.max_flow_items_per_ui_tick):
            flow_data = self.flow_data_queue.get()
            processed += 1

            if isinstance(flow_data, dict):
                # Discard anything older than Start Logging (attach-to-running-measurement behavior)
                epoch = flow_data.get('epoch', None)
                if (epoch is not None) and (self._logging_start_epoch is not None) and (epoch < self._logging_start_epoch):
                    continue

                flow_value = float(flow_data.get('flow_slm', 0.0) or 0.0)
                pressure_value = float(flow_data.get('pressure_pa', 0.0) or 0.0)
                temperature_value = float(flow_data.get('temperature_c', 0.0) or 0.0)

                latest_flow_value = flow_value
                latest_pressure_value = pressure_value
                latest_temperature_value = temperature_value

                if epoch is None:
                    # fall back to wall time if epoch was missing
                    epoch = time.time()

                if self._flow_epoch_zero is None:
                    self._flow_epoch_zero = epoch

                if self._flow_bin_start_epoch is None:
                    self._flow_bin_start_epoch = epoch

                # accumulate into current bin
                self._flow_bin_sum += flow_value
                self._flow_bin_pressure_sum += pressure_value
                self._flow_bin_temp_sum += temperature_value
                self._flow_bin_count += 1

                # emit bins based on *epoch* progression (not wall time)
                while ((epoch - self._flow_bin_start_epoch) >= self.flow_bin_seconds) and (emitted_bins < max_bins_to_emit_per_tick):
                    avg_flow = self._flow_bin_sum / max(self._flow_bin_count, 1)
                    avg_pressure = self._flow_bin_pressure_sum / max(self._flow_bin_count, 1)
                    avg_temp = self._flow_bin_temp_sum / max(self._flow_bin_count, 1)

                    # Timestamp for this emitted bin (end of the bin)
                    bin_epoch = self._flow_bin_start_epoch + self.flow_bin_seconds

                    # Log at 100 Hz (bin-based)
                    if self.is_logging and self.csv_writer:
                        timestamp_dt = datetime.datetime.fromtimestamp(bin_epoch)
                        unix_s = f"{bin_epoch:.3f}"
                        elapsed = bin_epoch - (self._logging_start_epoch or bin_epoch)
                        weight = self.last_scale_reading if self.last_scale_reading is not None else 0.0
                        stability = self.last_scale_stability if self.last_scale_stability is not None else 'N/A'

                        self.csv_writer.writerow([
                            timestamp_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                            unix_s,
                            f"{elapsed:.3f}",
                            f"{weight:.3f}",
                            f"{avg_flow:.6f}",
                            f"{avg_pressure:.2f}",
                            f"{avg_temp:.2f}",
                            stability
                        ])
                        self.record_count += 1

                        # Flush at most once per interval
                        now_ts = time.time()
                        if (now_ts - self._last_csv_flush_ts) >= self.csv_flush_interval_s:
                            try:
                                if self.log_file:
                                    self.log_file.flush()
                            except Exception:
                                pass
                            self._last_csv_flush_ts = now_ts

                    # Plot decimated (e.g., 10 Hz) but keep the internal deque dense by allowing more points if desired
                    self._flow_logged_bins_since_plot += 1
                    if self._flow_logged_bins_since_plot >= self._flow_plot_every_n:
                        plot_s = bin_epoch - (self._flow_epoch_zero or bin_epoch)
                        self.graph_timestamps.append(plot_s)
                        self.graph_scale_readings.append(self.last_scale_reading if self.last_scale_reading is not None else 0.0)
                        self.graph_flow_readings.append(avg_flow)
                        self._flow_logged_bins_since_plot = 0

                    # advance bin boundary and reset accumulators
                    self._flow_bin_start_epoch += self.flow_bin_seconds
                    self._flow_bin_sum = 0.0
                    self._flow_bin_pressure_sum = 0.0
                    self._flow_bin_temp_sum = 0.0
                    self._flow_bin_count = 0
                    emitted_bins += 1

        # Apply UI updates once per tick
        if latest_flow_value is not None:
            self.current_flow_reading_var.set(f"{latest_flow_value:.6f} slm")
            if latest_pressure_value is not None:
                self.current_pressure_reading_var.set(f"{latest_pressure_value:.2f} Pa")
            if latest_temperature_value is not None:
                self.current_temperature_reading_var.set(f"{latest_temperature_value:.2f} °C")

            # Don't force the status label here; it's handled by check_control_center_status()
            # (otherwise it masks file-growth based measuring/not-measuring and can look stuck)

        # Flush and UI counters at most once per tick (record count only)
        if (processed > 0) or (emitted_bins > 0):
            self.record_count_var.set(f"Records: {self.record_count}")

        # Schedule next check
        if not self.flow_data_queue.empty():
            self.root.after(10, self.check_data_queue)
        else:
            self.root.after(50, self.check_data_queue)
    
    def process_scale_data(self, line):
        """Process scale reading, update UI, and store latest value."""
        stable, reading = self.parse_scale_data(line)

        if reading is not None:
            self.last_scale_reading = reading
            self.last_scale_stability = 'S' if stable == 1 else 'U'
            self.current_scale_reading_var.set(f"{reading:.3f} g ({self.last_scale_stability})")
        else:
            self.log_message(f"Scale parse failed: {line}")
    
    def update_graph(self, frame):
        """Update the matplotlib graph"""
        if len(self.graph_timestamps) > 0:
            x = list(self.graph_timestamps)

            self.flow_line.set_data(x, list(self.graph_flow_readings))
            self.scale_line.set_data(x, list(self.graph_scale_readings))

            # Autoscale weight only; keep flow fixed scale by default
            self.ax_weight.relim()
            self.ax_weight.autoscale_view()

            # Keep flow on 0-50 by default; still relim X
            self.ax_flow.set_xlim(min(x), max(x))

        return self.flow_line, self.scale_line
    
    def log_message(self, message):
        """Add message to log display"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_display.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_display.see(tk.END)
    
    def on_close(self):
        """Clean up when closing"""
        if self.is_logging:
            self.stop_logging()
        
        self.stop_reading = True
        
        if self.scale_serial_connection and self.scale_serial_connection.is_open:
            self.scale_serial_connection.close()
        
        self.root.destroy()


def main():
    root = tk.Tk()
    app = ScaleFlowLogger(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
