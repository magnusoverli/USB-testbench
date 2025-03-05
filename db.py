"""
Database operations for USB flash drive benchmark tool.
"""
import os
import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

def get_db_path() -> str:
    """Get the path to the database file, creating directories if needed."""
    # Store in the project directory where the script is running
    project_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(project_dir, "data")
    
    # Create directory if it doesn't exist
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        
    return os.path.join(data_dir, "benchmark_results.db")

def init_database() -> None:
    """Initialize the database with required tables if they don't exist."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    
    # Create devices table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS devices (
        id INTEGER PRIMARY KEY,
        device_id TEXT UNIQUE,           -- Unique device identifier
        drive_letter TEXT,
        volume_name TEXT,
        size_gb REAL,
        model TEXT,
        vendor TEXT,
        serial_number TEXT,
        signature TEXT,
        pnp_device_id TEXT,
        firmware_revision TEXT,
        interface_type TEXT,
        media_type TEXT,
        first_seen TEXT,                 -- When first tested
        last_seen TEXT                   -- When last tested
    )''')
    
    # Create benchmark_sessions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS benchmark_sessions (
        id INTEGER PRIMARY KEY,
        device_id TEXT,                  -- References devices.device_id
        timestamp TEXT,
        test_type TEXT,                  -- "quick", "standard", "thorough", "custom"
        write_latency_files INTEGER,
        write_throughput_size_mb INTEGER,
        read_latency_files INTEGER,
        read_throughput_size_mb INTEGER,
        seek_count INTEGER,
        FOREIGN KEY (device_id) REFERENCES devices (device_id)
    )''')
    
    # Create benchmark_results table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS benchmark_results (
        id INTEGER PRIMARY KEY,
        session_id INTEGER,              -- References benchmark_sessions.id
        category TEXT,                   -- "write", "read", "seek"
        metric TEXT,                     -- e.g., "throughput_avg", "latency_min"
        value REAL,
        unit TEXT,                       -- e.g., "MB/s", "ms"
        FOREIGN KEY (session_id) REFERENCES benchmark_sessions (id)
    )''')
    
    conn.commit()
    conn.close()

def save_device_info(device_info: Dict) -> str:
    """
    Save or update device information in the database.
    Returns the unique device_id.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    
    # Extract the unique device identifier
    device_id = device_info['device_id']
    timestamp = datetime.now().isoformat()
    
    # Check if device already exists
    cursor.execute("SELECT id FROM devices WHERE device_id = ?", (device_id,))
    result = cursor.fetchone()
    
    if result:
        # Update existing device (last_seen and potentially changed properties)
        cursor.execute('''
        UPDATE devices SET 
            drive_letter = ?, 
            volume_name = ?, 
            size_gb = ?, 
            last_seen = ?
        WHERE device_id = ?
        ''', (
            device_info['DriveLetter'],
            device_info.get('VolumeName', 'No Label'),
            device_info['SizeGB'],
            timestamp,
            device_id
        ))
    else:
        # Insert new device
        cursor.execute('''
        INSERT INTO devices 
        (device_id, drive_letter, volume_name, size_gb, model, vendor, 
         serial_number, signature, pnp_device_id, firmware_revision,
         interface_type, media_type, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            device_id,
            device_info['DriveLetter'],
            device_info.get('VolumeName', 'No Label'),
            device_info['SizeGB'],
            device_info.get('Model', 'Unknown Model'),
            device_info.get('Vendor', 'Unknown Vendor'),
            device_info.get('SerialNumber', ''),
            device_info.get('Signature', ''),
            device_info.get('PNPDeviceID', ''),
            device_info.get('FirmwareRevision', ''),
            device_info.get('InterfaceType', ''),
            device_info.get('MediaType', ''),
            timestamp,
            timestamp
        ))
    
    conn.commit()
    conn.close()
    return device_id

def save_benchmark_results(device_id: str, test_type: str, test_params: Dict,
                          write_results: Dict, read_results: Dict, seek_results: Dict) -> int:
    """
    Save benchmark results to database.
    Returns the session ID.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    
    timestamp = datetime.now().isoformat()
    
    # Insert benchmark session
    cursor.execute('''
    INSERT INTO benchmark_sessions 
    (device_id, timestamp, test_type, 
     write_latency_files, write_throughput_size_mb,
     read_latency_files, read_throughput_size_mb, seek_count)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        device_id,
        timestamp,
        test_type,
        test_params.get('write_latency_file_count', 0),
        test_params.get('write_throughput_file_size_mb', 0),
        test_params.get('read_latency_file_count', 0),
        test_params.get('read_throughput_file_size_mb', 0),
        test_params.get('seek_count', 0)
    ))
    
    session_id = cursor.lastrowid
    
    # Process write results
    for key, value in write_results.items():
        category = "write"
        if "latency" in key:
            if key.endswith("avg") or key.endswith("min") or key.endswith("max") or key.endswith("median"):
                metric = key
                unit = "ms"
                # Convert seconds to milliseconds for storage
                value = value * 1000
            else:
                # Skip metadata like file_count
                continue
        elif "throughput" in key:
            if key.endswith("avg") or key.endswith("min") or key.endswith("max"):
                metric = key
                unit = "MB/s"
            else:
                # Skip metadata like file_size_mb
                continue
        else:
            # Unknown metric, store as-is
            metric = key
            unit = ""
            
        cursor.execute('''
        INSERT INTO benchmark_results 
        (session_id, category, metric, value, unit)
        VALUES (?, ?, ?, ?, ?)
        ''', (session_id, category, metric, value, unit))
    
    # Process read results
    for key, value in read_results.items():
        category = "read"
        if "latency" in key:
            if key.endswith("avg") or key.endswith("min") or key.endswith("max") or key.endswith("median"):
                metric = key
                unit = "ms"
                # Convert seconds to milliseconds for storage
                value = value * 1000
            else:
                # Skip metadata like file_count
                continue
        elif "throughput" in key:
            if key.endswith("avg") or key.endswith("min") or key.endswith("max"):
                metric = key
                unit = "MB/s"
            else:
                # Skip metadata like file_size_mb
                continue
        else:
            # Unknown metric, store as-is
            metric = key
            unit = ""
            
        cursor.execute('''
        INSERT INTO benchmark_results 
        (session_id, category, metric, value, unit)
        VALUES (?, ?, ?, ?, ?)
        ''', (session_id, category, metric, value, unit))
    
    # Process seek results
    for key, value in seek_results.items():
        category = "seek"
        if "latency" in key:
            if key.endswith("avg") or key.endswith("min") or key.endswith("max") or key.endswith("median"):
                metric = key
                unit = "ms"
                # Convert seconds to milliseconds for storage
                value = value * 1000
            else:
                # Skip metadata like num_seeks
                continue
        else:
            # Skip metadata like file_size_mb
            continue
            
        cursor.execute('''
        INSERT INTO benchmark_results 
        (session_id, category, metric, value, unit)
        VALUES (?, ?, ?, ?, ?)
        ''', (session_id, category, metric, value, unit))
    
    conn.commit()
    conn.close()
    return session_id

def get_device_history(device_id: str) -> List[Dict]:
    """
    Get benchmark history for a specific device.
    Returns a list of historical benchmark sessions and results.
    """
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row  # Enable dictionary access for rows
    cursor = conn.cursor()
    
    # Get all sessions for this device
    cursor.execute('''
    SELECT * FROM benchmark_sessions 
    WHERE device_id = ? 
    ORDER BY timestamp DESC
    ''', (device_id,))
    
    sessions = [dict(row) for row in cursor.fetchall()]
    
    # Get results for each session
    for session in sessions:
        cursor.execute('''
        SELECT category, metric, value, unit 
        FROM benchmark_results 
        WHERE session_id = ?
        ''', (session['id'],))
        
        results = [dict(row) for row in cursor.fetchall()]
        session['results'] = results
    
    conn.close()
    return sessions

def export_device_history(device_id: str, format: str = 'json') -> str:
    """
    Export device benchmark history to a file.
    Format can be 'json' or 'csv'.
    Returns the path to the exported file.
    """
    history = get_device_history(device_id)
    
    # Get device info for the filename
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM devices WHERE device_id = ?", (device_id,))
    device = dict(cursor.fetchone())
    conn.close()
    
    # Create safe filename
    safe_model = ''.join(c if c.isalnum() else '_' for c in device.get('model', 'unknown'))
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Export directory
    export_dir = os.path.join(os.path.expanduser("~"), "usb_benchmark_exports")
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)
    
    if format == 'json':
        # Create export data
        export_data = {
            "device": device,
            "benchmark_history": history
        }
        
        # Export to JSON
        filename = f"{safe_model}_{timestamp}.json"
        file_path = os.path.join(export_dir, filename)
        
        with open(file_path, 'w') as f:
            json.dump(export_data, f, indent=2)
            
        return file_path
    
    elif format == 'csv':
        # Export to CSV - more complex as we need to flatten the data
        filename = f"{safe_model}_{timestamp}.csv"
        file_path = os.path.join(export_dir, filename)
        
        with open(file_path, 'w') as f:
            # Write header
            f.write("Timestamp,Test Type,Category,Metric,Value,Unit\n")
            
            # Write data rows
            for session in history:
                timestamp = session['timestamp']
                test_type = session['test_type']
                
                for result in session['results']:
                    category = result['category']
                    metric = result['metric']
                    value = result['value']
                    unit = result['unit']
                    
                    f.write(f"{timestamp},{test_type},{category},{metric},{value},{unit}\n")
                    
        return file_path
    
    else:
        raise ValueError(f"Unsupported export format: {format}")