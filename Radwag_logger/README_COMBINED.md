# Radwag Scale + Sensirion Flow Logger

A Python application for simultaneous logging of data from:
- **Radwag scale** (connected via serial port - COM11, 9600 baud)
- **Sensirion SFM3300 flow sensor** (via SEK-SFM3xxx-AW/D Evaluation Kit using SensorBridge)

## Features

- **Dual sensor support**: Log both scale weight and flow rate simultaneously
- Real-time data display from both sensors
- Dual-axis graphing: Weight (g) on left axis, Flow rate (ml/min) on right axis
- CSV logging with timestamps for both sensors
- GUI interface with separate connect buttons for each sensor
- Real-time graph showing weight and flow over time
- Automatic file naming based on start time and date
- Live data visualization in scrollable text area
- Connection status monitoring for both sensors
- Visual distinction between stable and unstable scale readings
- Can log from either sensor independently or both together

## Requirements

- Python 3.6+
- pyserial
- tkinter (usually included with Python)
- pandas
- matplotlib
- sensirion-shdlc-sensorbridge
- sensirion-i2c-sfm-sf06

## Installation

1. Create and activate virtual environment (recommended):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install required packages:
```powershell
pip install -r requirements.txt
```

## Hardware Setup

### Radwag Scale
- Connect scale to COM11 (or modify the port in the GUI)
- Default baud rate: 9600

### Sensirion SFM3300 Flow Sensor
- Use the SEK-SFM3xxx-AW/D Evaluation Kit
- Connect the SensorBridge to a USB port (e.g., COM3)
- The SFM3300 sensor connects to the evaluation board via I2C

## Usage

1. Run the application:
```powershell
python scale_logger.py
```

2. **Connect sensors** (you can connect one or both):
   - Click "Connect Scale" to establish connection with the Radwag scale
   - Click "Connect Flow" to establish connection with the Sensirion flow sensor
   - Modify COM ports in the GUI if needed

3. **Start logging**: Click "Start Logging" to begin recording data to a CSV file (works with either or both sensors connected)

4. **Monitor data**: 
   - View real-time readings for both sensors
   - Watch the dual-axis graph: Blue line for weight, Green line for flow rate
   - Log display shows timestamped entries for both sensors

5. **Stop/Reset**: 
   - Use "Stop Logging" to pause logging 
   - Use "Reset" to clear the display and graph

6. **Graph controls**:
   - "Clear Graph" to reset only the graph data
   - Toggle "Auto Scale Y-axis" for manual zoom control (applies to weight axis)
   - Quick scale buttons for common weight ranges

## Output

CSV files are saved in the `data/` folder with the format:
`combined_log_YYYYMMDD_HHMMSS.csv`

The CSV contains five columns:
- **Timestamp** (YYYY-MM-DD HH:MM:SS.mmm)
- **Source** ("scale" or "flow")
- **Stable** (for scale: 1 = stable, 0 = unstable; for flow: always 1)
- **Value** (weight in grams OR flow rate in ml/min)
- **Secondary** (the other sensor's most recent value for synchronized logging)

### Example CSV entries:
```
Timestamp,Source,Stable,Value,Secondary
2026-02-19 10:30:15.123,scale,1,5.23,42.5
2026-02-19 10:30:15.223,flow,1,42.7,5.23
```

## Notes

- The flow sensor measures in standard liters per minute (slm) but values are automatically converted to ml/min for display
- Both sensors can run independently or together
- The graph updates every second
- Data is flushed immediately to ensure no loss on unexpected shutdown
- Temperature readings from the flow sensor are displayed but not currently logged to CSV

## Troubleshooting

- If you can't connect to the SensorBridge, check the COM port in Device Manager
- Make sure the SensorBridge is properly powered and the flow sensor is connected
- For the scale, ensure the correct COM port and baud rate are set
- If imports fail, reinstall the packages: `pip install -r requirements.txt`
