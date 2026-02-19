"""
Test script to verify Control Center log reading
Run this while Control Cente                for line in lines:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    # Skip header lines
                    if line.startswith('EdfVersion') or line.startswith('Date=') or \
                       line.startswith('Measurement') or line.startswith('Host') or \
                       line.startswith('Application') or line.startswith('Operating') or \
                       line.startswith('SensorId') or line.startswith('Type='):
                        skipped_headers += 1
                        continueng to see if flow data is being read correctly
Displays flow data in the console and plots it in real-time
"""

from pathlib import Path
import time
import datetime
import matplotlib.pyplot as plt
from collections import deque

class ControlCenterFlowReader:
    """Read flow data from Sensirion Control Center log files"""
    
    def __init__(self):
        self.log_directory = None
        self.current_log_file = None
        self.last_position = 0
        self.last_flow_value = None
        self.last_timestamp = None
        
    def find_log_directory(self):
        """Find Control Center log directory"""
        possible_paths = [
            Path("C:/Users/Alex/data_logging"),
        ]
        
        print("🔍 Searching for Control Center log directory...")
        for path in possible_paths:
            print(f"  Checking: {path}")
            if path.exists():
                print(f"  ✓ FOUND: {path}")
                return path
            else:
                print(f"    ✗ Not found")
        
        print("\n❌ No Control Center log directory found!")
        return None
    
    def find_latest_log_file(self, silent=False):
        """Find the most recently modified log file"""
        if not self.log_directory:
            self.log_directory = self.find_log_directory()
        
        if not self.log_directory or not self.log_directory.exists():
            return None
        
        log_files = list(self.log_directory.glob("*.edf")) + list(self.log_directory.glob("*.csv")) + list(self.log_directory.glob("*.txt"))
        
        if not log_files:
            if not silent:
                print(f"\n⚠ No log files (.edf, .csv or .txt) found in {self.log_directory}")
            return None
        
        if not silent:
            print(f"\n📁 Found {len(log_files)} log file(s):")
            for f in sorted(log_files, key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
                mod_time = datetime.datetime.fromtimestamp(f.stat().st_mtime)
                print(f"  - {f.name} (modified: {mod_time})")
        
        latest_file = max(log_files, key=lambda f: f.stat().st_mtime)
        if not silent:
            print(f"\n✓ Using latest: {latest_file.name}")
        return latest_file
    
    def read_all_data(self):
        """Read all data from the current log file"""
        if not self.current_log_file:
            return None
        
        all_data = []
        
        try:
            with open(self.current_log_file, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
                
                print(f"\n📖 Reading entire file ({len(all_lines)} lines)...")
                
                skipped_headers = 0
                skipped_columns = 0
                parse_errors = 0
                
                for line in all_lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Skip header lines (but not the column names line)
                    if line.startswith('EdfVersion') or line.startswith('Date=') or \
                       line.startswith('Measurement') or line.startswith('Host') or \
                       line.startswith('Application') or line.startswith('Operating') or \
                       line.startswith('SensorId') or line.startswith('Type='):
                        skipped_headers += 1
                        continue
                    
                    # Skip column header line (starts with "Epoch_UTC" but has column names)
                    if line.startswith('Epoch_UTC') and 'SFM' in line:
                        skipped_columns += 1
                        continue
                    
                    # Parse space-delimited EDF format
                    # Format: Epoch_UTC Flow(slm) Pressure(Pa) Temperature(°C)
                    parts = line.split()
                    
                    # Debug: print first few lines
                    if len(all_data) < 3:
                        print(f"  DEBUG: Parsing line with {len(parts)} parts: {parts[:6] if len(parts) > 6 else parts}")
                    
                    if len(parts) >= 4:
                        try:
                            epoch = float(parts[0])  # Epoch timestamp
                            flow_slm = float(parts[1])  # Flow in slm
                            pressure_pa = float(parts[2])  # Pressure in Pa
                            temperature_c = float(parts[3])  # Temperature in °C
                            # Convert epoch to ISO timestamp
                            from datetime import datetime
                            timestamp = datetime.fromtimestamp(epoch).isoformat()
                            
                            all_data.append({
                                'timestamp': timestamp,
                                'flow_slm': flow_slm,
                                'pressure_pa': pressure_pa,
                                'temperature_c': temperature_c
                            })
                        except (ValueError, IndexError):
                            continue
        
        except Exception as e:
            print(f"❌ Error reading log file: {e}")
            return None
        
        return all_data if all_data else None
    
    def read_new_data(self, silent=False, check_for_new_file=False):
        """Read new data from log file since last read"""
        # Check for newer file if requested
        if check_for_new_file or not self.current_log_file:
            latest_file = self.find_latest_log_file(silent=silent)
            if latest_file and latest_file != self.current_log_file:
                if not silent:
                    print(f"\n📄 Switched to newer file: {latest_file.name}")
                self.current_log_file = latest_file
                self.last_position = 0
        
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
                    
                    # Skip header lines (but not the column names line)
                    if line.startswith('EdfVersion') or line.startswith('Date=') or \
                       line.startswith('Measurement') or line.startswith('Host') or \
                       line.startswith('Application') or line.startswith('Operating') or \
                       line.startswith('SensorId') or line.startswith('Type='):
                        continue
                    
                    # Skip column header line (starts with "Epoch_UTC" but has column names)
                    if line.startswith('Epoch_UTC') and 'SFM' in line:
                        continue
                    
                    # Parse space-delimited EDF format
                    # Format: Epoch_UTC Flow(slm) Pressure(Pa) Temperature(°C)
                    parts = line.split()
                    
                    if len(parts) >= 4:
                        try:
                            epoch = float(parts[0])  # Epoch timestamp
                            flow_slm = float(parts[1])  # Flow in slm
                            pressure_pa = float(parts[2])  # Pressure in Pa
                            temperature_c = float(parts[3])  # Temperature in °C
                            # Convert epoch to ISO timestamp
                            from datetime import datetime
                            timestamp = datetime.fromtimestamp(epoch).isoformat()
                            
                            new_data.append({
                                'timestamp': timestamp,
                                'flow_slm': flow_slm,
                                'pressure_pa': pressure_pa,
                                'temperature_c': temperature_c
                            })
                            
                            self.last_flow_value = flow_slm
                            self.last_timestamp = timestamp
                        except (ValueError, IndexError):
                            continue
        
        except Exception as e:
            if not silent:
                print(f"❌ Error reading log file: {e}")
            return None
        
        return new_data if new_data else None
    
    def get_latest_flow(self):
        """Get most recent flow value"""
        new_data = self.read_new_data()
        
        if new_data:
            return new_data[-1]['flow_ml_per_min']
        
        return self.last_flow_value


def main():
    print("="*70)
    print("CONTROL CENTER LOG READER - LIVE DATA WITH PLOT")
    print("="*70)
    print("\n✓ Control Center writes buffered data every ~2.5 seconds")
    print("  - Sampling at 100 Hz")
    print("  - Buffer size: ~250 samples")
    print("  - Update interval: 2-3 seconds")
    print("\nThis gives you near-real-time data during measurement!")
    print("Close the plot window to stop.\n")
    
    reader = ControlCenterFlowReader()
    
    # Find log directory
    log_dir = reader.find_log_directory()
    if not log_dir:
        print("\n❌ Cannot continue without log directory.")
        return
    
    # Find latest file
    latest_file = reader.find_latest_log_file()
    if not latest_file:
        print("\n❌ No log files found!")
        return
    
    reader.current_log_file = latest_file
    
    # Read initial data
    print("\n" + "="*70)
    print("LOADING INITIAL DATA")
    print("="*70)
    
    all_data = reader.read_all_data()
    
    if not all_data:
        print("\n⚠ No data in file yet, waiting for data...")
        all_data = []
    else:
        print(f"\n✓ Loaded {len(all_data)} initial data points")
        flow_values = [d['flow_slm'] for d in all_data]
        print(f"  Flow range: {min(flow_values):.6f} - {max(flow_values):.6f} slm")
        print(f"  Latest: Flow={all_data[-1]['flow_slm']:.6f} slm, P={all_data[-1]['pressure_pa']:.2f} Pa, T={all_data[-1]['temperature_c']:.2f}°C")
    
    # Set up for monitoring
    if all_data:
        reader.last_flow_value = all_data[-1]['flow_slm']
        reader.last_timestamp = all_data[-1]['timestamp']
        with open(reader.current_log_file, 'r', encoding='utf-8', errors='ignore') as f:
            f.seek(0, 2)
            reader.last_position = f.tell()
    
    data_point_count = len(all_data)
    
    # Set up plot with 3 subplots
    plt.ion()  # Interactive mode
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10))
    
    # Keep last 60 seconds of data for plotting
    plot_times = deque(maxlen=6000)  # 60s * 100Hz
    plot_flows = deque(maxlen=6000)
    plot_pressures = deque(maxlen=6000)
    plot_temps = deque(maxlen=6000)
    
    # Add initial data to plot if available
    if all_data:
        from datetime import datetime
        first_epoch = datetime.fromisoformat(all_data[0]['timestamp']).timestamp()
        for point in all_data:
            epoch = datetime.fromisoformat(point['timestamp']).timestamp()
            plot_times.append(epoch - first_epoch)
            plot_flows.append(point['flow_slm'])
            plot_pressures.append(point['pressure_pa'])
            plot_temps.append(point['temperature_c'])
    
    line1, = ax1.plot([], [], 'b-', linewidth=1)
    ax1.set_ylabel('Flow (slm)')
    ax1.set_title('Live Sensor Data from Control Center')
    ax1.grid(True, alpha=0.3)
    
    line2, = ax2.plot([], [], 'g-', linewidth=1)
    ax2.set_ylabel('Pressure (Pa)')
    ax2.grid(True, alpha=0.3)
    
    line3, = ax3.plot([], [], 'r-', linewidth=1)
    ax3.set_xlabel('Time (seconds)')
    ax3.set_ylabel('Temperature (°C)')
    ax3.grid(True, alpha=0.3)
    
    fig.tight_layout()
    
    print("\n" + "="*70)
    print("MONITORING FOR NEW DATA")
    print("="*70)
    print("Time       | Flow (slm) | Pressure (Pa) | Temp (°C) | Points/s | Total")
    print("-" * 80)
    
    try:
        from datetime import datetime
        start_time = time.time()
        last_print_time = start_time
        last_plot_update = start_time
        last_file_check = start_time
        points_since_last_print = 0
        check_count = 0
        
        # Get reference epoch from first data point or current time
        if len(plot_times) > 0:
            first_epoch_offset = plot_times[0]  # Already calculated above
            reference_epoch = datetime.fromisoformat(all_data[0]['timestamp']).timestamp()
        else:
            reference_epoch = start_time
            first_epoch_offset = 0
        
        while plt.fignum_exists(fig.number):
            current_time = time.time()
            
            # Read new data from file every 1 second
            if current_time - last_file_check >= 1.0:
                check_count += 1
                
                # Check for new file every 10 file reads
                check_new_file = (check_count % 10 == 0)
                new_data = reader.read_new_data(silent=True, check_for_new_file=check_new_file)
                
                if new_data:
                    data_point_count += len(new_data)
                    points_since_last_print += len(new_data)
                    
                    # Add ALL data points to plot buffers using their actual timestamps
                    for point in new_data:
                        epoch = datetime.fromisoformat(point['timestamp']).timestamp()
                        plot_times.append(epoch - reference_epoch)
                        plot_flows.append(point['flow_slm'])
                        plot_pressures.append(point['pressure_pa'])
                        plot_temps.append(point['temperature_c'])
                    
                    latest = new_data[-1]
                    
                    # Print update every 3 seconds
                    if current_time - last_print_time >= 3.0:
                        elapsed = current_time - start_time
                        rate = points_since_last_print / (current_time - last_print_time)
                        
                        time_str = f"{int(elapsed//60):02d}:{int(elapsed%60):02d}"
                        print(f"{time_str:10s} | {latest['flow_slm']:10.6f} | {latest['pressure_pa']:13.2f} | {latest['temperature_c']:9.2f} | {rate:8.1f} | {data_point_count:6d}")
                        
                        last_print_time = current_time
                        points_since_last_print = 0
                
                last_file_check = current_time
            
            # Update plot at 10 Hz (every 0.1 seconds)
            if current_time - last_plot_update >= 0.1:
                if len(plot_times) > 0:
                    times_list = list(plot_times)
                    line1.set_data(times_list, list(plot_flows))
                    line2.set_data(times_list, list(plot_pressures))
                    line3.set_data(times_list, list(plot_temps))
                    
                    for ax in [ax1, ax2, ax3]:
                        ax.relim()
                        ax.autoscale_view()
                    
                    fig.canvas.draw()
                    fig.canvas.flush_events()
                    last_plot_update = current_time
            
            # Sleep briefly to avoid busy-waiting
            time.sleep(0.05)  # 20 Hz loop for smooth plotting
    
    except KeyboardInterrupt:
        pass
    finally:
        print("\n" + "="*70)
        print("STOPPED")
        print("="*70)
        elapsed = time.time() - start_time
        print(f"\nTotal runtime: {int(elapsed//60)}m {int(elapsed%60)}s")
        print(f"Total points: {data_point_count}")
        if reader.last_flow_value:
            print(f"Final flow value: {reader.last_flow_value:.6f} slm")
        plt.ioff()
        plt.show()


if __name__ == "__main__":
    main()
