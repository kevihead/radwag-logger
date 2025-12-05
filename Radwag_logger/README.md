# Radwag Scale Logger

A Python application for logging data from a Radwag scale connected via serial port (COM11, 9600 baud).

## Features

- Real-time data display from the scale
- CSV logging with timestamps
- GUI interface with start/stop/reset controls
- **Real-time graph showing weight over time**
- Automatic file naming based on start time and date
- Live data visualization in scrollable text area
- Connection status monitoring
- Visual distinction between stable and unstable readings

## Requirements

- Python 3.6+
- pyserial
- tkinter (usually included with Python)
- pandas
- matplotlib

## Installation

1. Install required packages:
```
pip install -r requirements.txt
```

## Usage

1. Connect your Radwag scale to COM port 11 (or modify the port in the GUI)
2. Run the application:
```
python scale_logger.py
```

3. Click "Connect" to establish connection with the scale
4. Click "Start Logging" to begin recording data to a CSV file
5. Use "Stop Logging" to pause logging or "Reset" to clear the display and graph
6. The real-time graph shows weight over time with green dots for stable readings and red dots for unstable readings
7. Use "Clear Graph" to reset only the graph data, or toggle "Auto Scale Y-axis" for manual zoom control

## Output

CSV files are saved in the `data/` folder with the format:
`scale_log_YYYYMMDD_HHMMSS.csv`

The CSV contains three columns:
- Timestamp (YYYY-MM-DD HH:MM:SS.mmm)
- Stable (1 = stable reading, 0 = unstable reading)
- Reading (numeric value without units)

The application parses the scale output format (e.g., "SI ? 0.00 g") to extract:
- Stability indicator: "?" means unstable (0), no "?" means stable (1)
- Numeric reading: extracts the value and removes units and formatting

You can modify the COM port and baud rate directly in the GUI interface before connecting.
