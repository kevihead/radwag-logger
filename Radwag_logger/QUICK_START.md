# Quick Start Guide

## What's New
Your Radwag scale logger now supports the Sensirion SFM3300 flow sensor!

## Changes Made:

### 1. **Updated Requirements**
- Added `sensirion-shdlc-sensorbridge`
- Added `sensirion-i2c-sfm-sf06`

### 2. **Enhanced GUI**
- Two separate connection sections: one for scale, one for flow sensor
- Separate "Connect Scale" and "Connect Flow" buttons
- Dual real-time displays showing both weight and flow rate
- Color-coded readings: Blue for weight, Green for flow rate

### 3. **Dual-Axis Graphing**
- Left Y-axis: Weight (g) - Blue line
- Right Y-axis: Flow rate (ml/min) - Green line
- X-axis: Time in seconds
- Both sensors plot on the same time axis for easy correlation

### 4. **Combined Data Logging**
CSV files now include data from both sensors:
- **Filename format**: `combined_log_YYYYMMDD_HHMMSS.csv`
- **Columns**: Timestamp, Source, Stable, Value, Secondary
- Each row tagged with source ("scale" or "flow")
- Synchronized logging - each entry includes the other sensor's most recent value

### 5. **Flexible Operation**
- Can connect and log from either sensor independently
- Can connect and log from both sensors simultaneously
- "Start Logging" button enables when at least one sensor is connected

## Hardware Setup

### Radwag Scale
- Connect to COM11 (default, changeable in GUI)
- Baud rate: 9600
- Same as before - no changes needed

### Sensirion SFM3300 Flow Sensor
1. Connect your SEK-SFM3xxx-AW/D Evaluation Kit to USB
2. Note the COM port (check Device Manager if needed)
3. Update the "Flow COM" field in the GUI (default is COM3)
4. The sensor connects via I2C to the SensorBridge
5. Flow measurements are in ml/min
6. Temperature is also displayed

## Quick Test

1. Activate your venv:
```powershell
.\.venv\Scripts\Activate.ps1
```

2. Run the application:
```powershell
python scale_logger.py
```

3. Connect your sensors (one or both):
   - Click "Connect Scale" for the Radwag scale
   - Click "Connect Flow" for the SFM3300 sensor

4. Start logging and watch both sensors in real-time!

## Tips
- The flow sensor auto-scales on its own Y-axis (right side)
- Weight axis can still be manually controlled with the existing controls
- Both sensors update at ~10 Hz
- Data is synchronized in the CSV - each entry includes context from the other sensor
- You can clear the graph while logging continues
- Temperature from the flow sensor is shown in the display but not logged to CSV (easy to add if needed)

## Troubleshooting
- **Can't connect to flow sensor?** Check the COM port in Device Manager
- **Import errors?** Run: `pip install sensirion-shdlc-sensorbridge sensirion-i2c-sfm-sf06`
- **Scale still works as before** - all existing functionality preserved
