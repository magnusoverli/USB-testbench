"""
Report generation functions for USB flash drive benchmark tool.
"""
import os
import json
import datetime
import bs4
from typing import List, Dict, Optional, Tuple, Any

def parse_existing_report(report_path: str) -> List[Dict]:
    """
    Parse an existing HTML report to extract device data.
    Returns a list of devices or an empty list if the file doesn't exist.
    """
    if not os.path.exists(report_path):
        return []
    
    try:
        from bs4 import BeautifulSoup
        
        with open(report_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
        
        # Extract device data from the table
        devices = []
        table = soup.find('table')
        
        if not table:
            return []
        
        rows = table.find_all('tr')[1:]  # Skip header row
        
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 7:  # Make sure we have enough columns
                device = {
                    'device': {
                        'friendly_name': cols[0].text.strip(),
                        'mount_point': None,  # Not in table, will be filled later
                        'vendor': None,       # Not in table, extracted from friendly_name
                        'model': None,        # Not in table, extracted from friendly_name
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
                
                # Try to extract more detailed info from device_info divs
                device_divs = soup.find_all('div', class_='device-info')
                for div in device_divs:
                    heading = div.find('h3')
                    if heading and heading.text.strip() == device['device']['friendly_name']:
                        # Extract vendor and model from the div
                        paras = div.find_all('p')
                        for p in paras:
                            text = p.text.strip()
                            if text.startswith('Vendor:'):
                                device['device']['vendor'] = text.replace('Vendor:', '').strip()
                            elif text.startswith('Model:'):
                                device['device']['model'] = text.replace('Model:', '').strip()
                            elif text.startswith('Mount Point:'):
                                device['device']['mount_point'] = text.replace('Mount Point:', '').strip()
                            elif text.startswith('GUID:'):
                                device['device']['guid'] = text.replace('GUID:', '').strip()
                            elif text.startswith('Size:'):
                                size_text = text.replace('Size:', '').strip()
                                if 'GB' in size_text:
                                    size_gb = float(size_text.replace('GB', '').strip())
                                    device['device']['size_bytes'] = int(size_gb * 1024 * 1024 * 1024)
                
                devices.append(device)
        
        return devices
    
    except Exception as e:
        print(f"Error parsing existing report: {e}")
        return []

def device_exists(devices: List[Dict], new_device: Dict) -> int:
    """
    Check if a device with the same friendly name exists in the list.
    Returns the index of the device if found, otherwise -1.
    """
    for i, device in enumerate(devices):
        if (device['device']['friendly_name'] == new_device['device']['friendly_name'] or
            (device['device'].get('guid') and new_device['device'].get('guid') and 
             device['device']['guid'] == new_device['device']['guid'])):
            return i
    return -1

def convert_benchmarks_to_device_data(drive_info: Dict, write_results: Dict, read_results: Dict, seek_results: Dict) -> Dict:
    """
    Convert benchmark results to device data format for storage.
    """
    size_gb = drive_info['SizeGB']
    size_bytes = int(size_gb * 1024 * 1024 * 1024)
    
    # Try to extract vendor and model from the drive info
    vendor = drive_info.get('Vendor', 'Unknown')
    model = drive_info.get('Model', drive_info.get('VolumeName', 'Unknown Device'))
    friendly_name = f"{vendor} {model}".strip()
    if friendly_name == "Unknown Unknown Device":
        friendly_name = f"Drive {drive_info['DriveLetter']}"
    
    # Create a device data object
    device_data = {
        'timestamp': datetime.datetime.now().isoformat(),
        'device': {
            'mount_point': drive_info['DriveLetter'],
            'device_path': None,
            'vendor': vendor,
            'model': model,
            'guid': drive_info.get('SerialNumber', None),
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

def generate_html_report(devices: List[Dict], output_path: str) -> None:
    """
    Generate an HTML report with benchmark results.
    
    Args:
        devices: List of device data dictionaries
        output_path: Path where to save the HTML report
    """
    # Sort devices by read throughput (descending)
    sorted_devices = sorted(devices, key=lambda d: d['throughput'].get('read_mbps', 0) 
                           if d['throughput'].get('read_mbps') is not None else 0, reverse=True)
    
    # Create device rows for the table
    device_rows = ""
    device_info_divs = ""
    
    # Prepare data for charts
    device_names = []
    write_latency = []
    read_latency = []
    random_read_latency = []
    write_throughput = []
    read_throughput = []
    
    for device in sorted_devices:
        # Skip devices with missing data
        if (device['latency'].get('read_ms') is None or 
            device['latency'].get('write_ms') is None or 
            device['throughput'].get('read_mbps') is None or 
            device['throughput'].get('write_mbps') is None):
            continue
        
        device_name = device['device']['friendly_name']
        device_names.append(device_name)
        
        # Add data for charts
        write_latency.append(device['latency']['write_ms'])
        read_latency.append(device['latency']['read_ms'])
        random_read_latency.append(device['latency']['random_read_ms'])
        write_throughput.append(device['throughput']['write_mbps'])
        read_throughput.append(device['throughput']['read_mbps'])
        
        # Format timestamp for display
        timestamp = device['timestamp']
        if 'T' in timestamp:
            timestamp = timestamp.split('T')[0] + ' ' + timestamp.split('T')[1][:5]
        
        # Add row to table
        device_rows += f"""
        <tr>
            <td>{device_name}</td>
            <td>{device['latency']['write_ms']:.2f}</td>
            <td>{device['latency']['read_ms']:.2f}</td>
            <td>{device['latency']['random_read_ms']:.2f}</td>
            <td>{device['throughput']['write_mbps']:.2f}</td>
            <td>{device['throughput']['read_mbps']:.2f}</td>
            <td class="timestamp">{timestamp}</td>
        </tr>
        """
        
        # Add detailed device info
        size_gb = device['device']['size_bytes'] / (1024 * 1024 * 1024)
        device_info_divs += f"""
        <div class="device-info">
            <h3>{device_name}</h3>
            <p><strong>Vendor:</strong> {device['device']['vendor']}</p>
            <p><strong>Model:</strong> {device['device']['model']}</p>
            <p><strong>Mount Point:</strong> {device['device']['mount_point']}</p>
            <p><strong>Device Path:</strong> {device['device'].get('device_path', 'None')}</p>
            <p><strong>GUID:</strong> {device['device'].get('guid', 'None')}</p>
            <p><strong>Size:</strong> {size_gb:.2f} GB</p>
            <p><strong>Last Tested:</strong> {timestamp}</p>
            
            <h4>Performance Results</h4>
            <p><strong>Write Latency:</strong> {device['latency']['write_ms']:.2f} ms</p>
            <p><strong>Read Latency:</strong> {device['latency']['read_ms']:.2f} ms</p>
            <p><strong>Random Read Latency:</strong> {device['latency']['random_read_ms']:.2f} ms</p>
            <p><strong>Write Throughput:</strong> {device['throughput']['write_mbps']:.2f} MB/s</p>
            <p><strong>Read Throughput:</strong> {device['throughput']['read_mbps']:.2f} MB/s</p>
        </div>
        """
    
    # Format data for JavaScript charts
    device_names_js = json.dumps(device_names)
    write_latency_js = json.dumps(write_latency)
    read_latency_js = json.dumps(read_latency)
    random_read_latency_js = json.dumps(random_read_latency)
    write_throughput_js = json.dumps(write_throughput)
    read_throughput_js = json.dumps(read_throughput)
    
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
        h1, h2 {{
            color: #2c3e50;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px 15px;
            border: 1px solid #ddd;
            text-align: left;
        }}
        th {{
            background-color: #f8f9fa;
            font-weight: bold;
        }}
        tr:nth-child(even) {{
            background-color: #f2f2f2;
        }}
        tr:hover {{
            background-color: #e9ecef;
        }}
        .best {{
            background-color: #d4edda;
        }}
        .worst {{
            background-color: #f8d7da;
        }}
        .device-info {{
            margin-bottom: 30px;
            padding: 15px;
            border: 1px solid #ddd;
            border-radius: 5px;
        }}
        .summary-chart {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            margin-bottom: 30px;
        }}
        .chart {{
            width: 48%;
            min-width: 300px;
            height: 300px;
            margin-bottom: 20px;
            border: 1px solid #ddd;
            padding: 10px;
            box-sizing: border-box;
        }}
        .timestamp {{
            font-size: 0.8em;
            color: #6c757d;
        }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <h1>USB Memory Stick Benchmark Results</h1>
    <p>Report generated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

    <div class="summary-chart">
        <div class="chart">
            <canvas id="latencyChart"></canvas>
        </div>
        <div class="chart">
            <canvas id="throughputChart"></canvas>
        </div>
    </div>

    <h2>Benchmark Results Summary</h2>
    <table>
        <tr>
            <th>Device</th>
            <th>Write Latency (ms)</th>
            <th>Read Latency (ms)</th>
            <th>Random Read Latency (ms)</th>
            <th>Write Throughput (MB/s)</th>
            <th>Read Throughput (MB/s)</th>
            <th>Last Tested</th>
        </tr>
        {device_rows}
    </table>

    <h2>Detailed Device Information</h2>
    {device_info_divs}

    <script>
        // Latency Chart
        const latencyCtx = document.getElementById('latencyChart').getContext('2d');
        new Chart(latencyCtx, {{
            type: 'bar',
            data: {{
                labels: {device_names_js},
                datasets: [
                    {{
                        label: 'Write Latency (ms)',
                        data: {write_latency_js},
                        backgroundColor: 'rgba(255, 99, 132, 0.5)',
                        borderColor: 'rgba(255, 99, 132, 1)',
                        borderWidth: 1
                    }},
                    {{
                        label: 'Read Latency (ms)',
                        data: {read_latency_js},
                        backgroundColor: 'rgba(54, 162, 235, 0.5)',
                        borderColor: 'rgba(54, 162, 235, 1)',
                        borderWidth: 1
                    }},
                    {{
                        label: 'Random Read Latency (ms)',
                        data: {random_read_latency_js},
                        backgroundColor: 'rgba(255, 206, 86, 0.5)',
                        borderColor: 'rgba(255, 206, 86, 1)',
                        borderWidth: 1
                    }}
                ]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{
                        beginAtZero: true,
                        title: {{
                            display: true,
                            text: 'Milliseconds (lower is better)'
                        }}
                    }}
                }},
                plugins: {{
                    title: {{
                        display: true,
                        text: 'Latency Comparison'
                    }}
                }}
            }}
        }});

        // Throughput Chart
        const throughputCtx = document.getElementById('throughputChart').getContext('2d');
        new Chart(throughputCtx, {{
            type: 'bar',
            data: {{
                labels: {device_names_js},
                datasets: [
                    {{
                        label: 'Write Throughput (MB/s)',
                        data: {write_throughput_js},
                        backgroundColor: 'rgba(75, 192, 192, 0.5)',
                        borderColor: 'rgba(75, 192, 192, 1)',
                        borderWidth: 1
                    }},
                    {{
                        label: 'Read Throughput (MB/s)',
                        data: {read_throughput_js},
                        backgroundColor: 'rgba(153, 102, 255, 0.5)',
                        borderColor: 'rgba(153, 102, 255, 1)',
                        borderWidth: 1
                    }}
                ]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{
                        beginAtZero: true,
                        title: {{
                            display: true,
                            text: 'MB/s (higher is better)'
                        }}
                    }}
                }},
                plugins: {{
                    title: {{
                        display: true,
                        text: 'Throughput Comparison'
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""
    
    # Write HTML to file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"Report saved to {output_path}")

def save_json_data(devices: List[Dict], output_path: str) -> None:
    """
    Save benchmark data to a JSON file.
    
    Args:
        devices: List of device data dictionaries
        output_path: Path where to save the JSON file
    """
    data = {"devices": devices}
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    print(f"Benchmark data saved to {output_path}")