"""
Report generation functions for USB flash drive benchmark tool with scalability features.
"""
import os
import json
import datetime
import math
from typing import List, Dict, Optional, Tuple, Any

def parse_existing_report(report_path: str) -> List[Dict]:
    """Parse an existing HTML report to extract device data."""
    if not os.path.exists(report_path):
        return []
    
    try:
        from bs4 import BeautifulSoup
        
        with open(report_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
        
        # Extract device data from the table
        devices = []
        table = soup.find('table', id='summary-table')
        
        if not table:
            return []
        
        rows = table.find_all('tr')[1:]  # Skip header row
        
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 7:  # Make sure we have enough columns
                device = {
                    'device': {
                        'friendly_name': cols[0].text.strip(),
                        'mount_point': None,
                        'vendor': None,
                        'model': None,
                    },
                    'latency': {
                        'write_ms': float(cols[1].text.strip()),
                        'read_ms': float(cols[2].text.strip()),
                        'random_read_ms': float(cols[3].text.strip()),
                    },
                    'throughput': {
                        'write_mbps': float(cols[4].text.strip()),
                        'read_mbps': float(cols[5].text.strip()),
                    },
                    'timestamp': cols[6].text.strip()
                }
                
                # Try to extract detailed device info
                device_div = soup.find('div', id=f"device-{len(devices)}")
                if device_div:
                    info_rows = device_div.find_all('tr')
                    for info_row in info_rows:
                        cells = info_row.find_all('td')
                        if len(cells) == 2:
                            key = cells[0].text.strip().replace(':', '')
                            value = cells[1].text.strip()
                            
                            if key == 'Vendor':
                                device['device']['vendor'] = value
                            elif key == 'Model':
                                device['device']['model'] = value
                            elif key == 'Mount Point':
                                device['device']['mount_point'] = value
                            elif key == 'GUID':
                                device['device']['guid'] = value
                            elif key == 'Size' and 'GB' in value:
                                size_gb = float(value.replace('GB', '').strip())
                                device['device']['size_bytes'] = int(size_gb * 1024 * 1024 * 1024)
                
                devices.append(device)
        
        return devices
    
    except Exception as e:
        print(f"Error parsing existing report: {e}")
        return []

def device_exists(devices: List[Dict], new_device: Dict) -> int:
    """Check if device exists in list. Returns index if found, otherwise -1."""
    for i, device in enumerate(devices):
        # Primary check: SerialNumber/GUID if available
        if (device['device'].get('guid') and new_device['device'].get('guid') and 
            device['device']['guid'] == new_device['device']['guid']):
            return i
            
        # Secondary check: Disk signature if available
        if (device['device'].get('signature') and new_device['device'].get('signature') and
            device['device']['signature'] == new_device['device']['signature']):
            return i
            
        # Tertiary check: Model + Size combo (less reliable)
        if (device['device'].get('model') == new_device['device'].get('model') and
            device['device'].get('size_bytes') and new_device['device'].get('size_bytes') and
            abs(device['device']['size_bytes'] - new_device['device']['size_bytes']) < 1024*1024*10): # 10MB tolerance
            
            # Additional check to reduce false positives - check volume name if available
            if (device['device'].get('volume_name') and new_device['device'].get('volume_name') and
                device['device']['volume_name'] == new_device['device']['volume_name']):
                return i
                
        # Fallback: Friendly name + size (least reliable)
        if (device['device']['friendly_name'] == new_device['device']['friendly_name'] and
            device['device'].get('size_bytes') and new_device['device'].get('size_bytes') and
            abs(device['device']['size_bytes'] - new_device['device']['size_bytes']) < 1024*1024*10): # 10MB tolerance
            return i
            
    return -1

def generate_device_fingerprint(device: Dict) -> str:
    """
    Generate a unique fingerprint for a device using available attributes.
    Returns a string hash that should be consistent for the same physical device.
    """
    # Collect all potential identifying attributes
    fingerprint_parts = []
    
    # Basic attributes that should be in every device
    if device['device'].get('mount_point'):
        fingerprint_parts.append(f"mount:{device['device']['mount_point']}")
        
    if device['device'].get('model'):
        fingerprint_parts.append(f"model:{device['device']['model']}")
        
    if device['device'].get('vendor'):
        fingerprint_parts.append(f"vendor:{device['device']['vendor']}")
        
    if device['device'].get('size_bytes'):
        # Round to nearest MB to account for minor size differences
        size_mb = device['device']['size_bytes'] // (1024 * 1024)
        fingerprint_parts.append(f"size_mb:{size_mb}")
        
    # Extended attributes that may be available from our enhanced detection
    extended_attrs = [
        'disk_index', 'device_id', 'volume_id', 'hardware_id', 'instance_id', 
        'disk_signature', 'firmware_version', 'physical_sector_size'
    ]
    
    for attr in extended_attrs:
        if device['device'].get(attr):
            fingerprint_parts.append(f"{attr}:{device['device'][attr]}")
            
    # If we have enough identifying information, compute a fingerprint
    if len(fingerprint_parts) >= 3:  # Need at least 3 attributes for reliability
        # Sort to ensure consistent order
        fingerprint_parts.sort()
        # Join all parts and create a hash
        import hashlib
        fingerprint_str = "|".join(fingerprint_parts)
        return hashlib.md5(fingerprint_str.encode()).hexdigest()
        
    return None

def convert_benchmarks_to_device_data(drive_info: Dict, write_results: Dict, read_results: Dict, seek_results: Dict) -> Dict:
    """Convert benchmark results to device data format."""
    size_gb = drive_info['SizeGB']
    size_bytes = int(size_gb * 1024 * 1024 * 1024)
    
    # Extract vendor and model
    vendor = drive_info.get('Vendor', 'Unknown')
    model = drive_info.get('Model', drive_info.get('VolumeName', 'Unknown Device'))
    friendly_name = f"{vendor} {model}".strip()
    if friendly_name == "Unknown Unknown Device":
        friendly_name = f"Drive {drive_info['DriveLetter']}"
    
    # Add uniqueness identifiers to friendly name if serial number is missing
    if not drive_info.get('SerialNumber'):
        if drive_info.get('Signature'):
            friendly_name += f" [Sig:{drive_info['Signature']}]"
        elif drive_info.get('FirmwareRevision'):
            friendly_name += f" [FW:{drive_info['FirmwareRevision']}]"
    
    # Create device data object
    device_data = {
        'timestamp': datetime.datetime.now().isoformat(),
        'device': {
            'mount_point': drive_info['DriveLetter'],
            'device_path': None,
            'vendor': vendor,
            'model': model,
            'guid': drive_info.get('SerialNumber', None),
            'signature': drive_info.get('Signature', None),
            'firmware_revision': drive_info.get('FirmwareRevision', None),
            'pnp_device_id': drive_info.get('PNPDeviceID', None),
            'interface_type': drive_info.get('InterfaceType', None),
            'media_type': drive_info.get('MediaType', None),
            'volume_name': drive_info.get('VolumeName', None),
            'size_bytes': size_bytes,
            'friendly_name': friendly_name
        },
        'latency': {
            'read_ms': read_results['read_latency_avg'] * 1000 if 'read_latency_avg' in read_results else None,
            'write_ms': write_results['write_latency_avg'] * 1000 if 'write_latency_avg' in write_results else None,
            'random_read_ms': seek_results['seek_latency_avg'] * 1000
        },
        'throughput': {
            'read_mbps': read_results['read_throughput_avg'] if 'read_throughput_avg' in read_results else None,
            'write_mbps': write_results['write_throughput_avg'] if 'write_throughput_avg' in write_results else None
        }
    }
    
    return device_data

def get_short_name(device: Dict) -> str:
    """Generate a short name for a device, removing common prefixes."""
    model_name = device['device']['model']
    if model_name and model_name.startswith("(Standard disk drives) "):
        return model_name.replace("(Standard disk drives) ", "")
    elif model_name:
        return model_name
    else:
        return device['device']['friendly_name'].split()[-1] if ' ' in device['device']['friendly_name'] else device['device']['friendly_name']

def remove_device_from_report(report_path: str, json_path: str, device_index: int) -> bool:
    """
    Remove a device from the HTML report and JSON data file.
    
    Args:
        report_path: Path to the HTML report file
        json_path: Path to the JSON data file
        device_index: Index of the device to remove
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Parse existing devices
        devices = parse_existing_report(report_path)
        
        # Validate index
        if device_index < 0 or device_index >= len(devices):
            print(f"Invalid device index: {device_index}")
            return False
            
        # Get device info for logging
        device_name = devices[device_index]['device']['friendly_name']
        
        # Remove the device
        devices.pop(device_index)
        
        # Generate new report
        generate_html_report(devices, report_path)
        
        # Update JSON data
        save_json_data(devices, json_path)
        
        print(f"Successfully removed device '{device_name}' from the report")
        return True
        
    except Exception as e:
        print(f"Error removing device: {e}")
        return False

def categorize_devices(devices: List[Dict]) -> Dict[str, List[Dict]]:
    """Group devices by manufacturer or other suitable category."""
    categories = {}
    
    for device in devices:
        vendor = device['device']['vendor']
        if vendor == "(Standard disk drives)":
            # Extract real vendor from model name if possible
            model = device['device']['model']
            if model:
                parts = model.split()
                if parts:
                    vendor = parts[0]  # Use first word of model name as vendor
        
        if not vendor or vendor == "Unknown":
            vendor = "Other"
            
        if vendor not in categories:
            categories[vendor] = []
            
        categories[vendor].append(device)
    
    return categories

def generate_html_report(devices: List[Dict], output_path: str) -> None:
    """Generate an HTML report with benchmark results, scalable for many devices."""
    # Sort devices by read throughput (descending)
    sorted_devices = sorted(devices, key=lambda d: d['throughput'].get('read_mbps', 0) 
                           if d['throughput'].get('read_mbps') is not None else 0, reverse=True)
    
    # Get top performers in each category
    top_write_latency = sorted(sorted_devices, key=lambda d: d['latency']['write_ms'])[:5]
    top_read_latency = sorted(sorted_devices, key=lambda d: d['latency']['read_ms'])[:5]
    top_write_throughput = sorted(sorted_devices, key=lambda d: -d['throughput']['write_mbps'])[:5]
    top_read_throughput = sorted(sorted_devices, key=lambda d: -d['throughput']['read_mbps'])[:5]
    
    # Create device rows for the summary table
    device_rows = ""

    for i, device in enumerate(sorted_devices):
        # Skip devices with missing data
        if (device['latency'].get('read_ms') is None or 
            device['latency'].get('write_ms') is None or 
            device['throughput'].get('read_mbps') is None or 
            device['throughput'].get('write_mbps') is None):
            continue
        
        device_name = device['device']['friendly_name']
        
        # Format timestamp for display
        timestamp = device['timestamp']
        if 'T' in timestamp:
            timestamp = timestamp.split('T')[0] + ' ' + timestamp.split('T')[1][:5]
        
        # Add row to table with Remove button
        device_rows += f"""
        <tr data-device-id="{i}">
            <td><label><input type="checkbox" class="device-selector" data-device-id="{i}"> {device_name}</label></td>
            <td>{device['latency']['write_ms']:.2f}</td>
            <td>{device['latency']['read_ms']:.2f}</td>
            <td>{device['latency']['random_read_ms']:.2f}</td>
            <td>{device['throughput']['write_mbps']:.2f}</td>
            <td>{device['throughput']['read_mbps']:.2f}</td>
            <td class="timestamp">{timestamp}</td>
            <td><button class="btn-action remove-device" data-device-id="{i}" title="Remove this device from the report">Remove</button></td>
        </tr>
        """
    
    # Create detailed info for each device
    device_details = ""
    for i, device in enumerate(sorted_devices):
        model = device['device']['model'] or "Unknown Model"
        vendor = device['device']['vendor'] or "Unknown Vendor"
        mount_point = device['device']['mount_point'] or "Unknown"
        guid = device['device'].get('guid', 'None')
        size_gb = device['device']['size_bytes'] / (1024 * 1024 * 1024) if device['device'].get('size_bytes') else 0
        
        timestamp = device['timestamp']
        if 'T' in timestamp:
            timestamp = timestamp.split('T')[0] + ' ' + timestamp.split('T')[1][:5]
        
        device_details += f"""
        <div id="device-{i}" class="device-detail" style="display:none;">
            <h3>{device['device']['friendly_name']}</h3>
            <table class="detail-table">
                <tr><td><strong>Vendor:</strong></td><td>{vendor}</td></tr>
                <tr><td><strong>Model:</strong></td><td>{model}</td></tr>
                <tr><td><strong>Mount Point:</strong></td><td>{mount_point}</td></tr>
                <tr><td><strong>GUID:</strong></td><td>{guid}</td></tr>
                <tr><td><strong>Size:</strong></td><td>{size_gb:.2f} GB</td></tr>
                <tr><td><strong>Last Tested:</strong></td><td>{timestamp}</td></tr>
                <tr><td colspan="2"><h4>Performance Results</h4></td></tr>
                <tr><td><strong>Write Latency:</strong></td><td>{device['latency']['write_ms']:.2f} ms</td></tr>
                <tr><td><strong>Read Latency:</strong></td><td>{device['latency']['read_ms']:.2f} ms</td></tr>
                <tr><td><strong>Random Read Latency:</strong></td><td>{device['latency']['random_read_ms']:.2f} ms</td></tr>
                <tr><td><strong>Write Throughput:</strong></td><td>{device['throughput']['write_mbps']:.2f} MB/s</td></tr>
                <tr><td><strong>Read Throughput:</strong></td><td>{device['throughput']['read_mbps']:.2f} MB/s</td></tr>
            </table>
        </div>
        """
    
    # Group devices by category for segmented viewing
    categories = categorize_devices(sorted_devices)
    category_options = ""
    for category in sorted(categories.keys()):
        category_options += f'<option value="{category}">{category} ({len(categories[category])})</option>'
    
    # Create comparison table
    comparison_headers = ""
    comparison_rows = ""
    
    # Properties for comparison
    properties = [
        ("Vendor", lambda d: d['device']['vendor']),
        ("Model", lambda d: d['device']['model']),
        ("Size", lambda d: f"{d['device']['size_bytes'] / (1024*1024*1024):.2f} GB" if d['device'].get('size_bytes') else "N/A"),
        ("Write Latency", lambda d: f"{d['latency']['write_ms']:.2f} ms"),
        ("Read Latency", lambda d: f"{d['latency']['read_ms']:.2f} ms"),
        ("Random Read Latency", lambda d: f"{d['latency']['random_read_ms']:.2f} ms"),
        ("Write Throughput", lambda d: f"{d['throughput']['write_mbps']:.2f} MB/s"),
        ("Read Throughput", lambda d: f"{d['throughput']['read_mbps']:.2f} MB/s"),
        ("Last Tested", lambda d: d['timestamp'].split('T')[0] + ' ' + d['timestamp'].split('T')[1][:5] if 'T' in d['timestamp'] else d['timestamp']),
    ]
    
    # Generate rows for the property table
    for prop_name, prop_getter in properties:
        comparison_rows += f'<tr class="comparison-row"><td><strong>{prop_name}</strong></td>'
        for i in range(5):  # Start with 5 empty slots
            comparison_rows += f'<td class="comparison-slot" id="prop-{prop_name.replace(" ", "-")}-{i}"></td>'
        comparison_rows += '</tr>'
    
    # Generate HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>USB Benchmark Results</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        h1, h2, h3 {{
            color: #2c3e50;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 10px;
            border: 1px solid #ddd;
            text-align: left;
        }}
        th {{
            background-color: #f8f9fa;
            font-weight: bold;
            position: sticky;
            top: 0;
        }}
        tr:nth-child(even) {{
            background-color: #f2f2f2;
        }}
        tr:hover {{
            background-color: #e9ecef;
        }}
        .summary-table {{
            max-height: 600px;
            overflow-y: auto;
        }}
        .tabs {{
            display: flex;
            margin-bottom: 10px;
            border-bottom: 1px solid #ddd;
        }}
        .tab {{
            padding: 8px 16px;
            cursor: pointer;
            background: #f5f5f5;
            border: 1px solid #ddd;
            border-bottom: none;
            margin-right: 4px;
            border-radius: 4px 4px 0 0;
        }}
        .tab.active {{
            background: #fff;
            border-bottom: 1px solid #fff;
            margin-bottom: -1px;
        }}
        .tab-content {{
            display: none;
            padding: 15px;
            border: 1px solid #ddd;
            border-top: none;
        }}
        .tab-content.active {{
            display: block;
        }}
        .chart-container {{
            position: relative;
            height: 300px;
            max-width: 100%;
            margin-bottom: 20px;
        }}
        .dashboard {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            margin-bottom: 20px;
        }}
        .metric-card {{
            width: 18%;
            min-width: 180px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 15px;
        }}
        .metric-value {{
            font-size: 24px;
            font-weight: bold;
            margin: 10px 0;
            color: #2c3e50;
        }}
        .metric-label {{
            font-size: 14px;
            color: #6c757d;
        }}
        .metric-unit {{
            font-size: 14px;
            color: #6c757d;
            margin-left: 5px;
        }}
        .controls {{
            margin: 15px 0;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 5px;
        }}
        .controls select, .controls input {{
            padding: 6px;
            margin-right: 10px;
        }}
        .controls button {{
            padding: 6px 12px;
            background: #2c3e50;
            color: white;
            border: none;
            border-radius: 3px;
            cursor: pointer;
        }}
        .controls button:hover {{
            background: #34495e;
        }}
        .device-detail {{
            margin-top: 20px;
            padding: 15px;
            border: 1px solid #ddd;
            border-radius: 5px;
        }}
        .detail-table {{
            width: 100%;
            margin-top: 10px;
        }}
        .detail-table td {{
            padding: 8px;
            border: 1px solid #ddd;
        }}
        .detail-table td:first-child {{
            width: 30%;
            background-color: #f8f9fa;
        }}
        .comparison-container {{
            margin-top: 20px;
            overflow-x: auto;
        }}
        .comparison-table {{
            min-width: 600px;
        }}
        .comparison-table th {{
            min-width: 120px;
        }}
        .comparison-slot {{
            min-width: 120px;
        }}
        .btn-action {{
            padding: 4px 8px;
            margin: 0 2px;
            background: #f8f9fa;
            border: 1px solid #ddd;
            border-radius: 3px;
            cursor: pointer;
            font-size: 12px;
        }}
        .btn-action:hover {{
            background: #e9ecef;
        }}
        .highlight {{
            background-color: #d4edda;
        }}
        .pagination {{
            display: flex;
            justify-content: center;
            margin-top: 15px;
        }}
        .pagination button {{
            padding: 5px 10px;
            margin: 0 5px;
            border: 1px solid #ddd;
            background: #fff;
            cursor: pointer;
        }}
        .pagination button.active {{
            background: #2c3e50;
            color: white;
        }}
        .search-box {{
            padding: 8px;
            width: 300px;
            margin-bottom: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }}
        .tooltip {{
            position: absolute;
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 5px 10px;
            border-radius: 3px;
            pointer-events: none;
            z-index: 100;
            font-size: 12px;
        }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js" integrity="sha256-+8RZJua0aEWg+QVVKg4LEzEEm/8RFez5Tb4JBNiV5xA=" crossorigin="anonymous"></script>
</head>
<body>
    <h1>USB Memory Stick Benchmark Results</h1>
    <p>Report generated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    
    <div class="controls">
        <input type="text" id="search-devices" class="search-box" placeholder="Search devices...">
        <select id="category-filter">
            <option value="all">All Categories</option>
            {category_options}
        </select>
        <select id="sort-by">
            <option value="read_throughput">Sort by Read Throughput</option>
            <option value="write_throughput">Sort by Write Throughput</option>
            <option value="read_latency">Sort by Read Latency</option>
            <option value="write_latency">Sort by Write Latency</option>
            <option value="random_latency">Sort by Random Read Latency</option>
        </select>
        <button id="compare-selected">Compare Selected</button>
        <button id="chart-selected">Chart Selected</button>
    </div>
    
    <div class="tabs">
        <div class="tab active" data-tab="summary">Summary</div>
        <div class="tab" data-tab="dashboard">Dashboard</div>
        <div class="tab" data-tab="details">Device Details</div>
        <div class="tab" data-tab="comparison">Compare</div>
        <div class="tab" data-tab="charts">Charts</div>
    </div>
    
    <div id="summary" class="tab-content active">
        <h2>Benchmark Results Summary</h2>
        <div class="summary-table">
            <table id="summary-table">
                <thead>
                    <tr>
                        <th>Device</th>
                        <th>Write Latency (ms)</th>
                        <th>Read Latency (ms)</th>
                        <th>Random Read Latency (ms)</th>
                        <th>Write Throughput (MB/s)</th>
                        <th>Read Throughput (MB/s)</th>
                        <th>Last Tested</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {device_rows}
                </tbody>
            </table>
        </div>
        <div class="pagination" id="summary-pagination"></div>
    </div>
    
    <div id="dashboard" class="tab-content">
        <h2>Performance Dashboard</h2>
        <div class="dashboard">
            <div class="metric-card">
                <div class="metric-label">Best Read Throughput</div>
                <div class="metric-value" id="best-read-throughput">
                    {top_read_throughput[0]['throughput']['read_mbps']:.1f}<span class="metric-unit">MB/s</span>
                </div>
                <div>{get_short_name(top_read_throughput[0])}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Best Write Throughput</div>
                <div class="metric-value" id="best-write-throughput">
                    {top_write_throughput[0]['throughput']['write_mbps']:.1f}<span class="metric-unit">MB/s</span>
                </div>
                <div>{get_short_name(top_write_throughput[0])}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Best Read Latency</div>
                <div class="metric-value" id="best-read-latency">
                    {top_read_latency[0]['latency']['read_ms']:.1f}<span class="metric-unit">ms</span>
                </div>
                <div>{get_short_name(top_read_latency[0])}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Best Write Latency</div>
                <div class="metric-value" id="best-write-latency">
                    {top_write_latency[0]['latency']['write_ms']:.1f}<span class="metric-unit">ms</span>
                </div>
                <div>{get_short_name(top_write_latency[0])}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total Devices</div>
                <div class="metric-value" id="total-devices">
                    {len(sorted_devices)}
                </div>
                <div>From {len(categories)} vendors</div>
            </div>
        </div>
        
        <div class="chart-container">
            <canvas id="topDevicesChart"></canvas>
        </div>
    </div>
    
    <div id="details" class="tab-content">
        <h2>Device Details</h2>
        <select id="device-selector">
            <option value="">Select a device...</option>
            {' '.join([f'<option value="{i}">{device["device"]["friendly_name"]}</option>' for i, device in enumerate(sorted_devices)])}
        </select>
        
        {device_details}
    </div>
    
    <div id="comparison" class="tab-content">
        <h2>Device Comparison</h2>
        <p>Select up to 5 devices from the summary tab to compare them side by side.</p>
        <div class="comparison-container">
            <table class="comparison-table">
                <thead>
                    <tr>
                        <th>Property</th>
                        <th id="comparison-device-0">Device 1</th>
                        <th id="comparison-device-1">Device 2</th>
                        <th id="comparison-device-2">Device 3</th>
                        <th id="comparison-device-3">Device 4</th>
                        <th id="comparison-device-4">Device 5</th>
                    </tr>
                </thead>
                <tbody>
                    {comparison_rows}
                </tbody>
            </table>
        </div>
    </div>
    
    <div id="charts" class="tab-content">
        <h2>Performance Charts</h2>
        <div class="controls">
            <select id="chart-metric">
                <option value="read_throughput">Read Throughput (MB/s)</option>
                <option value="write_throughput">Write Throughput (MB/s)</option>
                <option value="read_latency">Read Latency (ms)</option>
                <option value="write_latency">Write Latency (ms)</option>
                <option value="random_latency">Random Read Latency (ms)</option>
            </select>
            <select id="chart-limit">
                <option value="5">Top 5</option>
                <option value="10">Top 10</option>
                <option value="15">Top 15</option>
                <option value="all">All Devices</option>
            </select>
            <button id="update-chart">Update Chart</button>
        </div>
        <div class="chart-container">
            <canvas id="performanceChart"></canvas>
        </div>
    </div>

    <script>
        // Store all device data for client-side operations
        const allDevices = {json.dumps(sorted_devices)};
        let selectedDevices = [];
        const ITEMS_PER_PAGE = 15;
        let currentPage = 1;
        
        // Helper function to get short device name
        function getShortName(device) {{
            const model = device.device.model;
            if (model && model.startsWith("(Standard disk drives) ")) {{
                return model.replace("(Standard disk drives) ", "");
            }} else if (model) {{
                return model;
            }} else {{
                const fullName = device.device.friendly_name;
                return fullName.includes(' ') ? fullName.split(' ').pop() : fullName;
            }}
        }}
        
        // Initialize tabs
        document.querySelectorAll('.tab').forEach(tab => {{
            tab.addEventListener('click', () => {{
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                
                tab.classList.add('active');
                document.getElementById(tab.dataset.tab).classList.add('active');
                
                // Initialize charts when tab is selected
                if (tab.dataset.tab === 'dashboard') {{
                    initializeDashboardChart();
                }} else if (tab.dataset.tab === 'charts') {{
                    updatePerformanceChart();
                }}
            }});
        }});
        
        // Initialize dashboard chart
        function initializeDashboardChart() {{
            const ctx = document.getElementById('topDevicesChart').getContext('2d');
            const topReadDevices = [...allDevices].sort((a, b) => 
                b.throughput.read_mbps - a.throughput.read_mbps).slice(0, 5);
                
            const labels = topReadDevices.map(device => getShortName(device));
            const readData = topReadDevices.map(device => device.throughput.read_mbps);
            const writeData = topReadDevices.map(device => device.throughput.write_mbps);
            
            if (window.topDevicesChart) {{
                window.topDevicesChart.destroy();
            }}
            
            window.topDevicesChart = new Chart(ctx, {{
                type: 'bar',
                data: {{
                    labels: labels,
                    datasets: [
                        {{
                            label: 'Read Throughput (MB/s)',
                            data: readData,
                            backgroundColor: 'rgba(153, 102, 255, 0.5)',
                            borderColor: 'rgba(153, 102, 255, 1)',
                            borderWidth: 1
                        }},
                        {{
                            label: 'Write Throughput (MB/s)',
                            data: writeData,
                            backgroundColor: 'rgba(75, 192, 192, 0.5)',
                            borderColor: 'rgba(75, 192, 192, 1)',
                            borderWidth: 1
                        }}
                    ]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {{
                        y: {{
                            beginAtZero: true,
                            title: {{
                                display: true,
                                text: 'MB/s'
                            }}
                        }}
                    }},
                    plugins: {{
                        title: {{
                            display: true,
                            text: 'Top 5 Devices by Read Throughput'
                        }}
                    }}
                }}
            }});
        }}
        
        // Update performance chart based on selected options
        function updatePerformanceChart() {{
            const metric = document.getElementById('chart-metric').value;
            const limit = document.getElementById('chart-limit').value;
            const ctx = document.getElementById('performanceChart').getContext('2d');
            
            let metricPath, metricLabel, sortDirection, yAxisLabel;
            
            switch(metric) {{
                case 'read_throughput':
                    metricPath = device => device.throughput.read_mbps;
                    metricLabel = 'Read Throughput';
                    sortDirection = -1; // Higher is better
                    yAxisLabel = 'MB/s (higher is better)';
                    break;
                case 'write_throughput':
                    metricPath = device => device.throughput.write_mbps;
                    metricLabel = 'Write Throughput';
                    sortDirection = -1; // Higher is better
                    yAxisLabel = 'MB/s (higher is better)';
                    break;
                case 'read_latency':
                    metricPath = device => device.latency.read_ms;
                    metricLabel = 'Read Latency';
                    sortDirection = 1; // Lower is better
                    yAxisLabel = 'ms (lower is better)';
                    break;
                case 'write_latency':
                    metricPath = device => device.latency.write_ms;
                    metricLabel = 'Write Latency';
                    sortDirection = 1; // Lower is better
                    yAxisLabel = 'ms (lower is better)';
                    break;
                case 'random_latency':
                    metricPath = device => device.latency.random_read_ms;
                    metricLabel = 'Random Read Latency';
                    sortDirection = 1; // Lower is better
                    yAxisLabel = 'ms (lower is better)';
                    break;
            }}
            
            // Sort and limit devices
            let devicesToChart = [...allDevices].sort((a, b) => 
                sortDirection * (metricPath(a) - metricPath(b))
            );
            
            if (limit !== 'all') {{
                devicesToChart = devicesToChart.slice(0, parseInt(limit));
            }}
            
            const labels = devicesToChart.map(device => getShortName(device));
            const data = devicesToChart.map(metricPath);
            
            if (window.performanceChart) {{
                window.performanceChart.destroy();
            }}
            
            window.performanceChart = new Chart(ctx, {{
                type: 'bar',
                data: {{
                    labels: labels,
                    datasets: [{{
                        label: metricLabel,
                        data: data,
                        backgroundColor: 'rgba(54, 162, 235, 0.5)',
                        borderColor: 'rgba(54, 162, 235, 1)',
                        borderWidth: 1
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {{
                        y: {{
                            beginAtZero: true,
                            title: {{
                                display: true,
                                text: yAxisLabel
                            }}
                        }},
                        x: {{
                            ticks: {{
                                autoSkip: false,
                                maxRotation: 45,
                                minRotation: 45
                            }}
                        }}
                    }},
                    plugins: {{
                        title: {{
                            display: true,
                            text: `${{metricLabel}} Comparison`
                        }}
                    }}
                }}
            }});
        }}
        
        // Device details selector
        document.getElementById('device-selector').addEventListener('change', function() {{
            const deviceId = this.value;
            document.querySelectorAll('.device-detail').forEach(detail => {{
                detail.style.display = 'none';
            }});
            
            if (deviceId) {{
                document.getElementById(`device-${{deviceId}}`).style.display = 'block';
            }}
        }});
        
        // Setup pagination
        function setupPagination() {{
            const totalPages = Math.ceil(filteredDevices.length / ITEMS_PER_PAGE);
            const pagination = document.getElementById('summary-pagination');
            pagination.innerHTML = '';
            
            if (totalPages <= 1) return;
            
            // Previous button
            const prevBtn = document.createElement('button');
            prevBtn.textContent = '«';
            prevBtn.disabled = currentPage === 1;
            prevBtn.addEventListener('click', () => {{
                if (currentPage > 1) {{
                    currentPage--;
                    displayDevices();
                }}
            }});
            pagination.appendChild(prevBtn);
            
            // Page buttons
            for (let i = 1; i <= totalPages; i++) {{
                const pageBtn = document.createElement('button');
                pageBtn.textContent = i;
                pageBtn.classList.toggle('active', i === currentPage);
                pageBtn.addEventListener('click', () => {{
                    currentPage = i;
                    displayDevices();
                }});
                pagination.appendChild(pageBtn);
            }}
            
            // Next button
            const nextBtn = document.createElement('button');
            nextBtn.textContent = '»';
            nextBtn.disabled = currentPage === totalPages;
            nextBtn.addEventListener('click', () => {{
                if (currentPage < totalPages) {{
                    currentPage++;
                    displayDevices();
                }}
            }});
            pagination.appendChild(nextBtn);
        }}
        
        // Selected devices for comparison
        document.getElementById('compare-selected').addEventListener('click', () => {{
            if (selectedDevices.length === 0) {{
                alert('Please select at least one device to compare');
                return;
            }}
            
            // Show comparison tab
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelector('.tab[data-tab="comparison"]').classList.add('active');
            document.getElementById('comparison').classList.add('active');
            
            // Clear previous comparison
            for (let i = 0; i < 5; i++) {{
                document.getElementById(`comparison-device-${{i}}`).textContent = `Device ${{i+1}}`;
                document.getElementById(`comparison-device-${{i}}`).style.fontWeight = 'normal';
            }}
            
            document.querySelectorAll('.comparison-slot').forEach(slot => {{
                slot.textContent = '';
                slot.classList.remove('highlight');
            }});
            
            // Fill in comparison
            selectedDevices.slice(0, 5).forEach((deviceId, index) => {{
                const device = allDevices[deviceId];
                document.getElementById(`comparison-device-${{index}}`).textContent = getShortName(device);
                document.getElementById(`comparison-device-${{index}}`).style.fontWeight = 'bold';
                
                // Fill in properties
                document.getElementById(`prop-Vendor-${{index}}`).textContent = device.device.vendor || 'Unknown';
                document.getElementById(`prop-Model-${{index}}`).textContent = device.device.model || 'Unknown';
                document.getElementById(`prop-Size-${{index}}`).textContent = 
                    device.device.size_bytes ? 
                    `${{(device.device.size_bytes / (1024*1024*1024)).toFixed(2)}} GB` : 'Unknown';
                document.getElementById(`prop-Write-Latency-${{index}}`).textContent = `${{device.latency.write_ms.toFixed(2)}} ms`;
                document.getElementById(`prop-Read-Latency-${{index}}`).textContent = `${{device.latency.read_ms.toFixed(2)}} ms`;
                document.getElementById(`prop-Random-Read-Latency-${{index}}`).textContent = `${{device.latency.random_read_ms.toFixed(2)}} ms`;
                document.getElementById(`prop-Write-Throughput-${{index}}`).textContent = `${{device.throughput.write_mbps.toFixed(2)}} MB/s`;
                document.getElementById(`prop-Read-Throughput-${{index}}`).textContent = `${{device.throughput.read_mbps.toFixed(2)}} MB/s`;
                document.getElementById(`prop-Last-Tested-${{index}}`).textContent = 
                    device.timestamp.includes('T') ? 
                    `${{device.timestamp.split('T')[0]}} ${{device.timestamp.split('T')[1].substring(0, 5)}}` : 
                    device.timestamp;
            }});
            
            // Highlight best values
            highlightBestValues();
        }});
        
        function highlightBestValues() {{
            // Properties that are better when higher
            ['Write-Throughput', 'Read-Throughput'].forEach(prop => {{
                let bestValue = -Infinity;
                let bestIndex = -1;
                
                // Find best value
                for (let i = 0; i < Math.min(selectedDevices.length, 5); i++) {{
                    const cell = document.getElementById(`prop-${{prop}}-${{i}}`);
                    const value = parseFloat(cell.textContent);
                    if (value > bestValue) {{
                        bestValue = value;
                        bestIndex = i;
                    }}
                }}
                
                // Highlight best
                if (bestIndex >= 0) {{
                    document.getElementById(`prop-${{prop}}-${{bestIndex}}`).classList.add('highlight');
                }}
            }});
            
            // Properties that are better when lower
            ['Write-Latency', 'Read-Latency', 'Random-Read-Latency'].forEach(prop => {{
                let bestValue = Infinity;
                let bestIndex = -1;
                
                // Find best value
                for (let i = 0; i < Math.min(selectedDevices.length, 5); i++) {{
                    const cell = document.getElementById(`prop-${{prop}}-${{i}}`);
                    const value = parseFloat(cell.textContent);
                    if (value < bestValue) {{
                        bestValue = value;
                        bestIndex = i;
                    }}
                }}
                
                // Highlight best
                if (bestIndex >= 0) {{
                    document.getElementById(`prop-${{prop}}-${{bestIndex}}`).classList.add('highlight');
                }}
            }});
        }}
        
        // Device selection
        document.addEventListener('click', function(e) {{
            if (e.target.classList.contains('device-selector')) {{
                const deviceId = parseInt(e.target.dataset.deviceId);
                
                if (e.target.checked) {{
                    if (selectedDevices.length >= 5) {{
                        alert('You can only compare up to 5 devices at once');
                        e.target.checked = false;
                        return;
                    }}
                    selectedDevices.push(deviceId);
                }} else {{
                    selectedDevices = selectedDevices.filter(id => id !== deviceId);
                }}
            }}
        }});
        
        // Search functionality
        document.getElementById('search-devices').addEventListener('input', function() {{
            currentPage = 1;
            displayDevices();
        }});
        
        // Category filter
        document.getElementById('category-filter').addEventListener('change', function() {{
            currentPage = 1;
            displayDevices();
        }});
        
        // Sort by
        document.getElementById('sort-by').addEventListener('change', function() {{
            currentPage = 1;
            displayDevices();
        }});
        
        // Chart selected devices
        document.getElementById('chart-selected').addEventListener('click', function() {{
            if (selectedDevices.length === 0) {{
                alert('Please select at least one device to chart');
                return;
            }}
            
            // Switch to charts tab
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelector('.tab[data-tab="charts"]').classList.add('active');
            document.getElementById('charts').classList.add('active');
            
            // Create custom chart with selected devices
            createCustomChart();
        }});
        
        function createCustomChart() {{
            try {{
                console.log("Creating custom chart for selected devices:", selectedDevices);
                const ctx = document.getElementById('performanceChart').getContext('2d');
                const metric = document.getElementById('chart-metric').value;
                
                if (!ctx) {{
                    console.error("Canvas context not found");
                    alert("Error: Could not find the chart canvas");
                    return;
                }}
                
                let metricPath, metricLabel, yAxisLabel;
                
                switch(metric) {{
                    case 'read_throughput':
                        metricPath = device => device.throughput.read_mbps;
                        metricLabel = 'Read Throughput';
                        yAxisLabel = 'MB/s';
                        break;
                    case 'write_throughput':
                        metricPath = device => device.throughput.write_mbps;
                        metricLabel = 'Write Throughput';
                        yAxisLabel = 'MB/s';
                        break;
                    case 'read_latency':
                        metricPath = device => device.latency.read_ms;
                        metricLabel = 'Read Latency';
                        yAxisLabel = 'ms';
                        break;
                    case 'write_latency':
                        metricPath = device => device.latency.write_ms;
                        metricLabel = 'Write Latency';
                        yAxisLabel = 'ms';
                        break;
                    case 'random_latency':
                        metricPath = device => device.latency.random_read_ms;
                        metricLabel = 'Random Read Latency';
                        yAxisLabel = 'ms';
                        break;
                    default:
                        console.error("Unknown metric:", metric);
                        alert("Error: Unknown metric selected");
                        return;
                }}
                
                // Get data for selected devices
                const selectedDeviceData = [];
                for (const id of selectedDevices) {{
                    if (allDevices[id]) {{
                        selectedDeviceData.push(allDevices[id]);
                    }} else {{
                        console.warn("Device not found:", id);
                    }}
                }}
                
                console.log("Selected device data:", selectedDeviceData);
                
                if (selectedDeviceData.length === 0) {{
                    alert("No valid devices selected for charting");
                    return;
                }}
                
                // Get labels and data, handling potential errors
                const labels = [];
                const data = [];
                for (const device of selectedDeviceData) {{
                    try {{
                        // Use friendly name as fallback if getShortName fails
                        let shortName;
                        try {{
                            shortName = getShortName(device);
                        }} catch (e) {{
                            console.warn("Error in getShortName:", e);
                            shortName = device.device.friendly_name || "Unknown Device";
                        }}
                        labels.push(shortName);
                        
                        // Get metric value safely
                        const metricValue = metricPath(device);
                        data.push(metricValue !== null && metricValue !== undefined ? metricValue : 0);
                    }} catch (e) {{
                        console.error("Error processing device data:", e, device);
                    }}
                }}
                
                console.log("Chart labels:", labels);
                console.log("Chart data:", data);
                
                // Destroy existing chart if it exists
                if (window.performanceChart) {{
                    window.performanceChart.destroy();
                }}
                
                // Create new chart
                window.performanceChart = new Chart(ctx, {{
                    type: 'bar',
                    data: {{
                        labels: labels,
                        datasets: [{{
                            label: metricLabel,
                            data: data,
                            backgroundColor: 'rgba(54, 162, 235, 0.5)',
                            borderColor: 'rgba(54, 162, 235, 1)',
                            borderWidth: 1
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {{
                            y: {{
                                beginAtZero: true,
                                title: {{
                                    display: true,
                                    text: yAxisLabel
                                }}
                            }}
                        }},
                        plugins: {{
                            title: {{
                                display: true,
                                text: `Selected Devices: ${{metricLabel}} Comparison`
                            }}
                        }}
                    }}
                }});
                
                console.log("Chart created successfully");
            }} catch (e) {{
                console.error("Error creating chart:", e);
                alert("Error creating chart: " + e.message);
            }}
        }}
        
        // Chart update button
        document.getElementById('update-chart').addEventListener('click', updatePerformanceChart);
        
        // Filter devices based on search, category and sort criteria
        let filteredDevices = [];
        
        function filterDevices() {{
            const searchTerm = document.getElementById('search-devices').value.toLowerCase();
            const category = document.getElementById('category-filter').value;
            const sortBy = document.getElementById('sort-by').value;
            
            filteredDevices = allDevices.filter(device => {{
                // Search filter
                const deviceName = device.device.friendly_name.toLowerCase();
                const model = (device.device.model || '').toLowerCase();
                const vendor = (device.device.vendor || '').toLowerCase();
                
                const matchesSearch = deviceName.includes(searchTerm) || 
                                     model.includes(searchTerm) || 
                                     vendor.includes(searchTerm);
                
                // Category filter
                let matchesCategory = true;
                if (category !== 'all') {{
                    let deviceVendor = vendor;
                    if (deviceVendor === "(standard disk drives)") {{
                        // Extract vendor from model name
                        const modelParts = model.split(' ');
                        if (modelParts.length > 0) {{
                            deviceVendor = modelParts[0].toLowerCase();
                        }}
                    }}
                    matchesCategory = deviceVendor.includes(category.toLowerCase());
                }}
                
                return matchesSearch && matchesCategory;
            }});
            
            // Sort devices
            filteredDevices.sort((a, b) => {{
                switch(sortBy) {{
                    case 'read_throughput':
                        return b.throughput.read_mbps - a.throughput.read_mbps;
                    case 'write_throughput':
                        return b.throughput.write_mbps - a.throughput.write_mbps;
                    case 'read_latency':
                        return a.latency.read_ms - b.latency.read_ms;
                    case 'write_latency':
                        return a.latency.write_ms - b.latency.write_ms;
                    case 'random_latency':
                        return a.latency.random_read_ms - b.latency.random_read_ms;
                    default:
                        return 0;
                }}
            }});
        }}
        
        // Display filtered devices with pagination
        function displayDevices() {{
            filterDevices();
            setupPagination();
            
            const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
            const endIndex = Math.min(startIndex + ITEMS_PER_PAGE, filteredDevices.length);
            const deviceSubset = filteredDevices.slice(startIndex, endIndex);
            
            const tableBody = document.querySelector('#summary-table tbody');
            tableBody.innerHTML = '';
            
            deviceSubset.forEach((device, localIndex) => {{
                const deviceIndex = allDevices.findIndex(d => 
                    d.device.friendly_name === device.device.friendly_name);
                
                if (deviceIndex === -1) return;
                
                const row = document.createElement('tr');
                row.setAttribute('data-device-id', deviceIndex);
                
                // Format timestamp
                let timestamp = device.timestamp;
                if (timestamp.includes('T')) {{
                    timestamp = timestamp.split('T')[0] + ' ' + timestamp.split('T')[1].substring(0, 5);
                }}
                
                // Create row cells
                row.innerHTML = `
                    <td><label><input type="checkbox" class="device-selector" data-device-id="${{deviceIndex}}" 
                        ${{selectedDevices.includes(deviceIndex) ? 'checked' : ''}}> ${{device.device.friendly_name}}</label></td>
                    <td>${{device.latency.write_ms.toFixed(2)}}</td>
                    <td>${{device.latency.read_ms.toFixed(2)}}</td>
                    <td>${{device.latency.random_read_ms.toFixed(2)}}</td>
                    <td>${{device.throughput.write_mbps.toFixed(2)}}</td>
                    <td>${{device.throughput.read_mbps.toFixed(2)}}</td>
                    <td class="timestamp">${{timestamp}}</td>
                    <td><button class="btn-action remove-device" data-device-id="${{deviceIndex}}" title="Remove this device from the report">Remove</button></td>
                `;
                
                tableBody.appendChild(row);
            }});
            
            // Show message if no results
            if (deviceSubset.length === 0) {{
                const row = document.createElement('tr');
                row.innerHTML = `<td colspan="8" style="text-align: center;">No devices found matching your criteria</td>`;
                tableBody.appendChild(row);
            }}
        }}
        
        // Initialize the page
        document.addEventListener('DOMContentLoaded', function() {{
            displayDevices();
        }});

    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('remove-device')) {
            const deviceId = parseInt(e.target.dataset.deviceId);
            const deviceName = allDevices[deviceId].device.friendly_name;
            
            if (confirm(`Are you sure you want to remove "${deviceName}" from the report?`)) {
                // Create a form to submit the removal request
                const form = document.createElement('form');
                form.method = 'POST';
                form.action = 'remove_device.py';
                form.style.display = 'none';
                
                // Add the device ID
                const idField = document.createElement('input');
                idField.type = 'hidden';
                idField.name = 'device_id';
                idField.value = deviceId;
                form.appendChild(idField);
                
                // Add script path as reference
                const scriptPath = document.createElement('input');
                scriptPath.type = 'hidden';
                scriptPath.name = 'script_path';
                scriptPath.value = window.location.pathname;
                form.appendChild(scriptPath);
                
                // Submit the form
                document.body.appendChild(form);
                form.submit();
            }
        }
    });
    </script>
</body>
</html>
"""
    
    # Write HTML to file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"Report saved to {output_path}")

def save_json_data(devices: List[Dict], output_path: str) -> None:
    """Save benchmark data to a JSON file."""
    data = {"devices": devices}
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    print(f"Benchmark data saved to {output_path}")