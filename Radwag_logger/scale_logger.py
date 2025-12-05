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

class ScaleLogger:
    def __init__(self, root):
        self.root = root
        self.root.title("Radwag Scale Logger")
        self.root.geometry("1200x800")
        
        # Serial connection parameters
        self.com_port = "COM11"
        self.baud_rate = 9600
        self.serial_connection = None
        
        # Logging variables
        self.is_logging = False
        self.log_file = None
        self.csv_writer = None
        self.start_time = None
        
        # Threading and data queue
        self.data_queue = queue.Queue()
        self.read_thread = None
        self.stop_reading = False
        
        # Graph data storage (keep last 1000 points for better data retention)
        self.graph_timestamps = deque(maxlen=1000)
        self.graph_readings = deque(maxlen=1000)
        self.graph_stability = deque(maxlen=1000)
        self.graph_start_time = None  # For relative time calculation
        
        # Setup GUI
        self.setup_gui()
        self.setup_graph()
        
        # Start checking for data
        self.check_data_queue()
        
    def setup_gui(self):
        # Create main paned window for resizable layout
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left frame for controls and data display
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=1)
        
        # Right frame for graph
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=2)
        
        # Configure grid weights for left frame
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(2, weight=1)
        
        # Connection settings
        settings_frame = ttk.LabelFrame(left_frame, text="Connection Settings", padding="5")
        settings_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Single row with all connection info
        ttk.Label(settings_frame, text="COM Port:").grid(row=0, column=0, sticky=tk.W)
        self.com_port_var = tk.StringVar(value=self.com_port)
        ttk.Entry(settings_frame, textvariable=self.com_port_var, width=10).grid(row=0, column=1, padx=(5, 20))
        
        ttk.Label(settings_frame, text="Baud Rate:").grid(row=0, column=2, sticky=tk.W)
        self.baud_rate_var = tk.StringVar(value=str(self.baud_rate))
        ttk.Entry(settings_frame, textvariable=self.baud_rate_var, width=10).grid(row=0, column=3, padx=(5, 20))
        
        self.status_var = tk.StringVar(value="Disconnected")
        status_label = ttk.Label(settings_frame, textvariable=self.status_var, font=('Arial', 10, 'bold'))
        status_label.grid(row=0, column=4, sticky=tk.W, padx=(5, 0))
        
        # Control buttons
        button_frame = ttk.Frame(left_frame)
        button_frame.grid(row=1, column=0, pady=(0, 10))
        
        self.connect_btn = ttk.Button(button_frame, text="Connect", command=self.connect_scale)
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.start_btn = ttk.Button(button_frame, text="Start Logging", command=self.start_logging, state='disabled')
        self.start_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.stop_btn = ttk.Button(button_frame, text="Stop Logging", command=self.stop_logging, state='disabled')
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.reset_btn = ttk.Button(button_frame, text="Reset", command=self.reset_logging)
        self.reset_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # Data display
        data_frame = ttk.LabelFrame(left_frame, text="Live Data", padding="5")
        data_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        data_frame.columnconfigure(0, weight=1)
        data_frame.rowconfigure(1, weight=1)
        
        # Current reading
        current_frame = ttk.Frame(data_frame)
        current_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        current_frame.columnconfigure(1, weight=1)
        
        self.current_reading_var = tk.StringVar(value="No data")
        current_reading_label = ttk.Label(current_frame, textvariable=self.current_reading_var, 
                                        font=('Arial', 14, 'bold'), foreground='black')
        current_reading_label.grid(row=0, column=0, sticky=tk.W)
        
        # Log display (reduced height for graph)
        self.log_display = scrolledtext.ScrolledText(data_frame, height=10, width=50)
        self.log_display.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Log info
        info_frame = ttk.Frame(left_frame)
        info_frame.grid(row=3, column=0, sticky=(tk.W, tk.E))
        
        # Logging status with colored indicator
        log_status_frame = ttk.Frame(info_frame)
        log_status_frame.pack(side=tk.LEFT)
        
        self.log_status_indicator = tk.Label(log_status_frame, text="●", font=('Arial', 20), fg='red')
        self.log_status_indicator.pack(side=tk.LEFT, padx=(0, 5), anchor='center')
        
        self.log_info_var = tk.StringVar(value="No active log file")
        log_info_label = ttk.Label(log_status_frame, textvariable=self.log_info_var, font=('Arial', 12))
        log_info_label.pack(side=tk.LEFT, anchor='center')
        
        self.record_count_var = tk.StringVar(value="Records: 0")
        ttk.Label(info_frame, textvariable=self.record_count_var, font=('Arial', 10)).pack(side=tk.RIGHT)
        
        # Setup graph in right frame
        self.graph_frame = right_frame
        
    def setup_graph(self):
        """Setup the matplotlib graph"""
        # Create figure and subplot
        plt.style.use('default')
        self.fig, self.ax = plt.subplots(figsize=(8, 6))
        self.fig.patch.set_facecolor('white')
        
        # Configure the plot
        self.ax.set_xlabel('Time (seconds)')
        self.ax.set_ylabel('Reading (g)')
        self.ax.grid(True, alpha=0.3)
        
        # Initialize single line for all readings (no color coding)
        self.reading_line, = self.ax.plot([], [], 'b-', linewidth=1, label='Weight')
        
        # No legend needed
        # self.ax.legend(loc='upper right')
        
        # Set initial default limits
        self.ax.set_xlim(0, 60)  # Start with 60 seconds range
        self.ax.set_ylim(-5, 10)  # Default -5 to 10g range
        
        # Set initial ticks for default range
        self.set_smart_y_ticks(-5, 10)
        
        # Enable both major and minor grids
        self.ax.grid(True, which='major', alpha=0.5, linewidth=0.8)
        self.ax.grid(True, which='minor', alpha=0.3, linewidth=0.5)
        
        # Embed plot in tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, self.graph_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Add graph controls
        graph_controls = ttk.Frame(self.graph_frame)
        graph_controls.pack(fill=tk.X, padx=5, pady=(0, 5))
        
        # First row of controls
        controls_row1 = ttk.Frame(graph_controls)
        controls_row1.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Button(controls_row1, text="Clear Graph", command=self.clear_graph).pack(side=tk.LEFT)
        
        self.auto_scale_var = tk.BooleanVar(value=False)  # Start with manual mode
        auto_scale_check = ttk.Checkbutton(controls_row1, text="Auto Scale Y-axis", 
                                         variable=self.auto_scale_var, 
                                         command=self.on_autoscale_toggle)
        auto_scale_check.pack(side=tk.LEFT, padx=(10, 0))
        
        # Second row - Manual Y-axis controls
        controls_row2 = ttk.Frame(graph_controls)
        controls_row2.pack(fill=tk.X)
        
        ttk.Label(controls_row2, text="Y-axis:").pack(side=tk.LEFT)
        
        ttk.Label(controls_row2, text="Min:").pack(side=tk.LEFT, padx=(10, 2))
        self.y_min_var = tk.StringVar(value="-5")
        y_min_entry = ttk.Entry(controls_row2, textvariable=self.y_min_var, width=6)
        y_min_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Label(controls_row2, text="Max:").pack(side=tk.LEFT, padx=(5, 2))
        self.y_max_var = tk.StringVar(value="10")
        y_max_entry = ttk.Entry(controls_row2, textvariable=self.y_max_var, width=6)
        y_max_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(controls_row2, text="Apply", command=self.apply_manual_y_scale).pack(side=tk.LEFT, padx=(5, 0))
        
        # Quick scale buttons
        ttk.Label(controls_row2, text="Quick scale:").pack(side=tk.LEFT, padx=(15, 5))
        ttk.Button(controls_row2, text="-5:10", command=lambda: self.set_quick_scale(-5, 10)).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(controls_row2, text="0:50", command=lambda: self.set_quick_scale(0, 50)).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(controls_row2, text="0:100", command=lambda: self.set_quick_scale(0, 100)).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(controls_row2, text="0:1000", command=lambda: self.set_quick_scale(0, 1000)).pack(side=tk.LEFT, padx=(0, 2))
        
        # Initialize graph update
        self.update_graph()
        
    def on_autoscale_toggle(self):
        """Handle auto-scale checkbox toggle"""
        # Don't modify anything when toggling - just let the update cycle handle it
        # The manual fields should only be updated by explicit user actions
        
    def apply_manual_y_scale(self):
        """Apply manually entered Y-axis limits"""
        try:
            y_min = float(self.y_min_var.get())
            y_max = float(self.y_max_var.get())
            
            if y_min >= y_max:
                messagebox.showerror("Error", "Y-min must be less than Y-max")
                return
                
            self.auto_scale_var.set(False)  # Disable auto scale
            
            # Set exact limits without any padding or adjustment
            self.ax.set_ylim(y_min, y_max)
            self.set_smart_y_ticks(y_min, y_max)
            
            # Force exact limits again after setting ticks (in case matplotlib expanded them)
            self.ax.set_ylim(y_min, y_max)
            
            # Force immediate update without auto-scaling interference
            self.canvas.draw_idle()
            
        except ValueError:
            messagebox.showerror("Error", "Please enter valid numbers for Y-axis limits")
    
    def set_quick_scale(self, y_min, y_max):
        """Set Y-axis to predefined quick scale"""
        
        # Disable auto-scaling first
        self.auto_scale_var.set(False)
        
        # Set the values
        self.y_min_var.set(str(y_min))
        self.y_max_var.set(str(y_max))
        
        # Apply the manual scale
        self.apply_manual_y_scale()
    
    def get_nice_limits(self, data_min, data_max):
        """Calculate nice round limits for auto-scaling"""
        if abs(data_max - data_min) < 0.001:
            # Very small range, use default
            return -5, 10
        
        # Calculate range and determine appropriate rounding
        data_range = data_max - data_min
        
        if data_range < 1:
            # Sub-gram range, round to 0.5g
            nice_min = round((data_min - 0.5) * 2) / 2
            nice_max = round((data_max + 0.5) * 2) / 2
        elif data_range < 10:
            # Small range, round to nearest gram
            nice_min = int(data_min - 1)
            nice_max = int(data_max + 2)
        elif data_range < 50:
            # Medium range, round to nearest 5g
            nice_min = (int(data_min / 5) - 1) * 5
            nice_max = (int(data_max / 5) + 2) * 5
        elif data_range < 200:
            # Large range, round to nearest 10g
            nice_min = (int(data_min / 10) - 1) * 10
            nice_max = (int(data_max / 10) + 2) * 10
        else:
            # Very large range, round to nearest 50g
            nice_min = (int(data_min / 50) - 1) * 50
            nice_max = (int(data_max / 50) + 2) * 50
        
        # Ensure minimum range
        if nice_max - nice_min < 5:
            center = (nice_min + nice_max) / 2
            nice_min = center - 2.5
            nice_max = center + 2.5
        
        return nice_min, nice_max
        
    def clear_graph(self):
        """Clear the graph data"""
        self.graph_timestamps.clear()
        self.graph_readings.clear()
        self.graph_stability.clear()
        self.graph_start_time = None  # Reset start time
        self.update_graph()
        
    def update_graph(self):
        """Update the graph with current data"""
        try:
            if len(self.graph_timestamps) == 0:
                # Clear the line if no data
                self.reading_line.set_data([], [])
            else:
                # Convert timestamps to relative seconds
                if self.graph_start_time is None:
                    self.graph_start_time = self.graph_timestamps[0]
                
                # Calculate relative times in seconds
                relative_times = []
                for timestamp in self.graph_timestamps:
                    relative_time = (timestamp - self.graph_start_time).total_seconds()
                    relative_times.append(relative_time)
                
                # Update single line with all readings
                self.reading_line.set_data(relative_times, list(self.graph_readings))
                
                # Update X-axis (time) with smart tick spacing
                if relative_times:
                    time_min = 0
                    time_max = max(relative_times)
                    
                    # Add some padding
                    time_padding = max(time_max * 0.05, 5)  # At least 5 seconds padding
                    x_max = time_max + time_padding
                    
                    self.ax.set_xlim(time_min, x_max)
                    
                    # Set smart X-axis ticks based on time range
                    self.set_smart_x_ticks(time_max)
                
                # Update Y-axis - ONLY auto-scale if checkbox is checked AND we have data
                if self.auto_scale_var.get() and len(self.graph_readings) > 0:
                    y_values = list(self.graph_readings)
                    data_min = min(y_values)
                    data_max = max(y_values)
                    
                    # Get nice round limits
                    y_min, y_max = self.get_nice_limits(data_min, data_max)
                    
                    self.ax.set_ylim(y_min, y_max)
                    
                    # Update the manual control fields to show current auto values
                    self.y_min_var.set(str(int(y_min) if y_min == int(y_min) else y_min))
                    self.y_max_var.set(str(int(y_max) if y_max == int(y_max) else y_max))
                    
                    # Set smart Y-axis ticks (whole grams only)
                    self.set_smart_y_ticks(y_min, y_max)
                else:
                    # Manual mode - enforce the manual Y limits from the input fields
                    try:
                        manual_y_min = float(self.y_min_var.get())
                        manual_y_max = float(self.y_max_var.get())
                        current_ylim = self.ax.get_ylim()
                        
                        # Only update if the current limits don't match manual settings
                        if abs(current_ylim[0] - manual_y_min) > 0.001 or abs(current_ylim[1] - manual_y_max) > 0.001:
                            self.ax.set_ylim(manual_y_min, manual_y_max)
                        
                        # Set ticks and then force the limits again (in case ticks expanded them)
                        self.set_smart_y_ticks(manual_y_min, manual_y_max)
                        self.ax.set_ylim(manual_y_min, manual_y_max)  # Force exact limits after ticks
                        
                    except ValueError:
                        # If manual fields have invalid values, just update ticks for current limits
                        current_ylim = self.ax.get_ylim()
                        self.set_smart_y_ticks(current_ylim[0], current_ylim[1])
            
            # Redraw the canvas
            self.canvas.draw_idle()
            
        except Exception as e:
            pass  # Silent error handling for graph updates
        
        # Schedule next update
        self.root.after(1000, self.update_graph)
        
    def set_smart_x_ticks(self, time_max):
        """Set smart X-axis ticks based on time range"""
        try:
            if time_max <= 60:  # Less than 1 minute
                # Major ticks every 10 seconds, minor every 5 seconds
                major_interval = 10
                minor_interval = 5
            elif time_max <= 300:  # Less than 5 minutes
                # Major ticks every 30 seconds, minor every 10 seconds
                major_interval = 30
                minor_interval = 10
            elif time_max <= 1200:  # Less than 20 minutes
                # Major ticks every 2 minutes, minor every 30 seconds
                major_interval = 120
                minor_interval = 30
            elif time_max <= 3600:  # Less than 1 hour
                # Major ticks every 5 minutes, minor every minute
                major_interval = 300
                minor_interval = 60
            else:  # More than 1 hour
                # Major ticks every 10 minutes, minor every 5 minutes
                major_interval = 600
                minor_interval = 300
            
            # Generate major tick positions
            major_ticks = []
            current_tick = 0
            while current_tick <= time_max + major_interval:
                major_ticks.append(current_tick)
                current_tick += major_interval
            
            # Generate minor tick positions
            minor_ticks = []
            current_tick = 0
            while current_tick <= time_max + minor_interval:
                if current_tick not in major_ticks:  # Don't duplicate major ticks
                    minor_ticks.append(current_tick)
                current_tick += minor_interval
            
            # Limit to maximum 10 major ticks to prevent overflow
            if len(major_ticks) > 10:
                step = len(major_ticks) // 10 + 1
                major_ticks = major_ticks[::step]
            
            self.ax.set_xticks(major_ticks)
            self.ax.set_xticks(minor_ticks, minor=True)
            
        except Exception as e:
            pass  # Silent error handling for X-tick setting
    
    def set_smart_y_ticks(self, y_min, y_max):
        """Set smart Y-axis ticks (whole grams only) with minor ticks"""
        try:
            # Calculate whole gram ticks
            y_range = y_max - y_min
            
            if y_range <= 10:
                # For small ranges, major every gram, minor every 0.5g
                major_interval = 1
                minor_interval = 0.5
            elif y_range <= 50:
                # For medium ranges, major every 5 grams, minor every 1g
                major_interval = 5
                minor_interval = 1
            elif y_range <= 100:
                # For larger ranges, major every 10 grams, minor every 5g
                major_interval = 10
                minor_interval = 5
            else:
                # For very large ranges, major every 20 grams, minor every 10g
                major_interval = 20
                minor_interval = 10
            
            # Generate major ticks - ONLY within the specified range
            start_major = int(y_min // major_interval) * major_interval
            if start_major < y_min:
                start_major += major_interval
            
            major_ticks = []
            current_tick = start_major
            while current_tick <= y_max:
                major_ticks.append(current_tick)
                current_tick += major_interval
            
            # Generate minor ticks - ONLY within the specified range
            start_minor = int(y_min // minor_interval) * minor_interval
            if start_minor < y_min:
                start_minor += minor_interval
            
            minor_ticks = []
            current_tick = start_minor
            while current_tick <= y_max:
                if current_tick not in major_ticks:
                    minor_ticks.append(current_tick)
                current_tick += minor_interval
            
            # Ensure we don't have too many ticks (max 15 major)
            if len(major_ticks) > 15:
                step = len(major_ticks) // 15 + 1
                major_ticks = major_ticks[::step]
            
            self.ax.set_yticks(major_ticks)
            self.ax.set_yticks(minor_ticks, minor=True)
            
        except Exception as e:
            pass  # Silent error handling for Y-tick setting
        
    def connect_scale(self):
        try:
            if self.serial_connection and self.serial_connection.is_open:
                self.disconnect_scale()
                return
                
            self.com_port = self.com_port_var.get()
            self.baud_rate = int(self.baud_rate_var.get())
            
            self.serial_connection = serial.Serial(
                port=self.com_port,
                baudrate=self.baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            
            self.status_var.set("Connected")
            self.connect_btn.config(text="Disconnect")
            self.start_btn.config(state='normal')
            
            # Start reading thread
            self.stop_reading = False
            self.read_thread = threading.Thread(target=self.read_scale_data)
            self.read_thread.daemon = True
            self.read_thread.start()
            
        except Exception as e:
            messagebox.showerror("Connection Error", f"Failed to connect to {self.com_port}: {str(e)}")
            
    def disconnect_scale(self):
        self.stop_reading = True
        if self.read_thread:
            self.read_thread.join(timeout=2)
            
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
            
        self.status_var.set("Disconnected")
        self.connect_btn.config(text="Connect")
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='disabled')
        
    def read_scale_data(self):
        while not self.stop_reading and self.serial_connection and self.serial_connection.is_open:
            try:
                if self.serial_connection.in_waiting > 0:
                    data = self.serial_connection.readline().decode('utf-8').strip()
                    if data:
                        timestamp = datetime.datetime.now()
                        self.data_queue.put((timestamp, data))
                time.sleep(0.1)
            except Exception as e:
                pass  # Silent error handling for data reading
                break
                
    def check_data_queue(self):
        try:
            while True:
                timestamp, data = self.data_queue.get_nowait()
                self.process_scale_data(timestamp, data)
        except queue.Empty:
            pass
        
        # Schedule next check
        self.root.after(100, self.check_data_queue)
        
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

    def process_scale_data(self, timestamp, data):
        # Parse the scale data
        stable, reading = self.parse_scale_data(data)
        
        # Add to graph data if parsing successful
        if stable is not None and reading is not None:
            # Set start time on first data point
            if self.graph_start_time is None:
                self.graph_start_time = timestamp
                
            self.graph_timestamps.append(timestamp)
            self.graph_readings.append(reading)
            self.graph_stability.append(stable == 1)
        
        # Update current reading display
        if stable is not None and reading is not None:
            stability_text = "Stable" if stable else "Unstable"
            display_text = f"{reading:.2f} g ({stability_text})"
            self.current_reading_var.set(display_text)
        else:
            self.current_reading_var.set(data)  # Show raw data if parsing fails
        
        # Add to log display
        formatted_time = timestamp.strftime("%H:%M:%S.%f")[:-3]  # Include milliseconds
        if stable is not None and reading is not None:
            stability_text = "S" if stable else "U"
            log_entry = f"[{formatted_time}] {reading:.2f} g [{stability_text}]\n"
        else:
            log_entry = f"[{formatted_time}] {data} [RAW]\n"
        
        self.log_display.insert(tk.END, log_entry)
        self.log_display.see(tk.END)
        
        # Limit log display to last 1000 lines
        lines = self.log_display.get("1.0", tk.END).split("\n")
        if len(lines) > 1000:
            self.log_display.delete("1.0", f"{len(lines)-1000}.0")
        
        # Write to CSV if logging
        if self.is_logging and self.csv_writer:
            if stable is not None and reading is not None:
                self.csv_writer.writerow([
                    timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                    stable,
                    reading
                ])
            else:
                # Fallback for unparseable data
                self.csv_writer.writerow([
                    timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                    "ERROR",
                    data
                ])
            self.log_file.flush()  # Ensure data is written immediately
            
            # Update record count
            current_count = int(self.record_count_var.get().split(": ")[1])
            self.record_count_var.set(f"Records: {current_count + 1}")
            
    def start_logging(self):
        if not self.serial_connection or not self.serial_connection.is_open:
            messagebox.showerror("Error", "Please connect to the scale first")
            return
            
        try:
            # Create data folder if it doesn't exist
            script_dir = os.path.dirname(os.path.abspath(__file__))
            data_folder = os.path.join(script_dir, "data")
            os.makedirs(data_folder, exist_ok=True)
            
            # Create filename with start time
            self.start_time = datetime.datetime.now()
            filename = self.start_time.strftime("scale_log_%Y%m%d_%H%M%S.csv")
            filepath = os.path.join(data_folder, filename)
            
            # Create CSV file
            self.log_file = open(filepath, 'w', newline='')
            self.csv_writer = csv.writer(self.log_file)
            
            # Write header
            self.csv_writer.writerow(['Timestamp', 'Stable', 'Reading'])
            
            self.is_logging = True
            self.start_btn.config(state='disabled')
            self.stop_btn.config(state='normal')
            self.log_info_var.set(f"Logging to: data/{filename}")
            self.record_count_var.set("Records: 0")
            
            # Update logging status indicator to green
            self.log_status_indicator.config(fg='green')
            
        except Exception as e:
            messagebox.showerror("Logging Error", f"Failed to start logging: {str(e)}")
            
    def stop_logging(self):
        self.is_logging = False
        
        if self.log_file:
            self.log_file.close()
            self.log_file = None
            self.csv_writer = None
            
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        
        # Update logging status indicator to red
        self.log_status_indicator.config(fg='red')
        
        if self.start_time:
            duration = datetime.datetime.now() - self.start_time
            self.log_info_var.set(f"Logging stopped. Duration: {str(duration).split('.')[0]}")
        else:
            self.log_info_var.set("Logging stopped")
            
    def reset_logging(self):
        self.stop_logging()
        self.log_display.delete('1.0', tk.END)
        self.current_reading_var.set("No data")
        self.log_info_var.set("No active log file")
        self.record_count_var.set("Records: 0")
        self.clear_graph()
        
        # Ensure logging status indicator is red
        self.log_status_indicator.config(fg='red')
        
    def on_closing(self):
        self.stop_logging()
        self.disconnect_scale()
        self.root.destroy()

def main():
    root = tk.Tk()
    app = ScaleLogger(root)
    
    # Handle window close
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    # Start the GUI
    root.mainloop()

if __name__ == "__main__":
    main()
