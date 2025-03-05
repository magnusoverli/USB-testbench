"""
Web application for visualizing USB flash drive benchmark results.
"""
from flask import Flask, render_template, request, jsonify
import json
import os
import sqlite3
from datetime import datetime

# Get the path to the database
import db

app = Flask(__name__)
app.config['SECRET_KEY'] = 'usb-benchmark-visualization'

def dict_factory(cursor, row):
    """Convert SQLite row to dictionary for JSON serialization."""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def get_db_connection():
    """Get a connection to the SQLite database with row factory."""
    conn = sqlite3.connect(db.get_db_path())
    conn.row_factory = dict_factory
    return conn

@app.route('/')
def index():
    """Render the main dashboard page."""
    return render_template('index.html')

@app.route('/devices')
def get_devices():
    """Get all devices from the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT * FROM devices
    ORDER BY last_seen DESC
    ''')
    
    devices = cursor.fetchall()
    conn.close()
    
    return render_template('devices.html', devices=devices)

@app.route('/device/<device_id>')
def device_detail(device_id):
    """Get detailed information and benchmarks for a specific device."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get device info
    cursor.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,))
    device = cursor.fetchone()
    
    if not device:
        conn.close()
        return "Device not found", 404
    
    # Get all benchmark sessions for this device
    cursor.execute('''
    SELECT * FROM benchmark_sessions 
    WHERE device_id = ? 
    ORDER BY timestamp DESC
    ''', (device_id,))
    
    sessions = cursor.fetchall()
    
    # Get results for each session
    for session in sessions:
        cursor.execute('''
        SELECT category, metric, value, unit 
        FROM benchmark_results 
        WHERE session_id = ?
        ''', (session['id'],))
        
        results = cursor.fetchall()
        session['results'] = results
    
    conn.close()
    
    return render_template('device_detail.html', device=device, sessions=sessions)

@app.route('/api/devices')
def api_devices():
    """API endpoint to get all devices as JSON."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT * FROM devices
    ORDER BY last_seen DESC
    ''')
    
    devices = cursor.fetchall()
    conn.close()
    
    return jsonify(devices)

@app.route('/api/device/<device_id>/sessions')
def api_device_sessions(device_id):
    """API endpoint to get all benchmark sessions for a device."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT * FROM benchmark_sessions 
    WHERE device_id = ? 
    ORDER BY timestamp DESC
    ''', (device_id,))
    
    sessions = cursor.fetchall()
    conn.close()
    
    return jsonify(sessions)

@app.route('/api/session/<int:session_id>/results')
def api_session_results(session_id):
    """API endpoint to get all results for a benchmark session."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT * FROM benchmark_results 
    WHERE session_id = ?
    ''', (session_id,))
    
    results = cursor.fetchall()
    conn.close()
    
    return jsonify(results)

@app.route('/compare', methods=['GET', 'POST'])
def compare_devices():
    """Compare multiple devices or sessions."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get all devices for selection
    cursor.execute('SELECT * FROM devices ORDER BY last_seen DESC')
    all_devices = cursor.fetchall()
    
    if request.method == 'POST':
        # Get selected devices from form
        selected_devices = request.form.getlist('devices')
        
        comparison_data = {}
        
        for device_id in selected_devices:
            # Get device info
            cursor.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,))
            device = cursor.fetchone()
            
            # Get the most recent session
            cursor.execute('''
            SELECT * FROM benchmark_sessions 
            WHERE device_id = ? 
            ORDER BY timestamp DESC
            LIMIT 1
            ''', (device_id,))
            
            session = cursor.fetchone()
            
            if session:
                cursor.execute('''
                SELECT category, metric, value, unit 
                FROM benchmark_results 
                WHERE session_id = ?
                ''', (session['id'],))
                
                results = cursor.fetchall()
                
                # Structure the data for comparison
                device_data = {
                    'info': device,
                    'session': session,
                    'results': {}
                }
                
                # Organize results by category and metric
                for result in results:
                    category = result['category']
                    metric = result['metric']
                    
                    if category not in device_data['results']:
                        device_data['results'][category] = {}
                    
                    device_data['results'][category][metric] = {
                        'value': result['value'],
                        'unit': result['unit']
                    }
                
                comparison_data[device_id] = device_data
        
        conn.close()
        return render_template('comparison.html', 
                              devices=all_devices, 
                              selected_devices=selected_devices,
                              comparison_data=comparison_data)
    
    conn.close()
    return render_template('comparison.html', devices=all_devices, selected_devices=[], comparison_data={})

def create_templates():
    """Create the necessary template files if they don't exist."""
    templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    
    # Create directories if they don't exist
    for directory in [templates_dir, static_dir, os.path.join(static_dir, 'css'), os.path.join(static_dir, 'js')]:
        if not os.path.exists(directory):
            os.makedirs(directory)
    
    # Define the templates
    templates = {
        'base.html': """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}USB Flash Drive Benchmark Results{% endblock %}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    {% block head %}{% endblock %}
</head>
<body>
    <header>
        <h1>USB Flash Drive Benchmark</h1>
        <nav>
            <ul>
                <li><a href="{{ url_for('index') }}">Dashboard</a></li>
                <li><a href="{{ url_for('get_devices') }}">Devices</a></li>
                <li><a href="{{ url_for('compare_devices') }}">Compare</a></li>
            </ul>
        </nav>
    </header>
    
    <main>
        {% block content %}{% endblock %}
    </main>
    
    <footer>
        <p>USB Flash Drive Benchmark Tool - Performance Visualization</p>
    </footer>
    
    {% block scripts %}{% endblock %}
</body>
</html>""",
        
        'index.html': """{% extends 'base.html' %}

{% block title %}Dashboard - USB Benchmark{% endblock %}

{% block content %}
<div class="dashboard">
    <h2>Benchmark Dashboard</h2>
    
    <div class="dashboard-summary">
        <div class="summary-card" id="device-count">
            <h3>Devices Tested</h3>
            <p class="count">Loading...</p>
        </div>
        
        <div class="summary-card" id="test-count">
            <h3>Total Tests Run</h3>
            <p class="count">Loading...</p>
        </div>
        
        <div class="summary-card">
            <h3>Last Test</h3>
            <p id="last-test-date">Loading...</p>
        </div>
    </div>
    
    <div class="chart-container">
        <div class="chart-card">
            <h3>Top Read Performance</h3>
            <canvas id="read-chart"></canvas>
        </div>
        
        <div class="chart-card">
            <h3>Top Write Performance</h3>
            <canvas id="write-chart"></canvas>
        </div>
    </div>
    
    <div class="chart-container">
        <div class="chart-card">
            <h3>Fastest Access Times</h3>
            <canvas id="latency-chart"></canvas>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
document.addEventListener('DOMContentLoaded', function() {
    // Load device data
    fetch('/api/devices')
        .then(response => response.json())
        .then(devices => {
            document.getElementById('device-count').querySelector('.count').textContent = devices.length;
            
            if (devices.length > 0) {
                const lastDevice = devices[0];
                document.getElementById('last-test-date').textContent = new Date(lastDevice.last_seen).toLocaleString();
            }
            
            // Process device data for charts
            const deviceNames = [];
            const readSpeeds = [];
            const writeSpeeds = [];
            const latencies = [];
            
            // We'll need to load additional data for each device
            const promises = devices.map(device => {
                return fetch(`/api/device/${device.device_id}/sessions`)
                    .then(response => response.json())
                    .then(sessions => {
                        if (sessions.length > 0) {
                            // Use the most recent session
                            const latestSession = sessions[0];
                            
                            return fetch(`/api/session/${latestSession.id}/results`)
                                .then(response => response.json())
                                .then(results => {
                                    const readResult = results.find(r => r.category === 'read' && r.metric === 'read_throughput_avg');
                                    const writeResult = results.find(r => r.category === 'write' && r.metric === 'write_throughput_avg');
                                    const latencyResult = results.find(r => r.category === 'seek' && r.metric === 'seek_latency_avg');
                                    
                                    if (readResult && writeResult && latencyResult) {
                                        const displayName = `${device.model || 'Unknown'} (${device.drive_letter})`;
                                        deviceNames.push(displayName);
                                        readSpeeds.push({
                                            name: displayName,
                                            speed: readResult.value
                                        });
                                        writeSpeeds.push({
                                            name: displayName,
                                            speed: writeResult.value
                                        });
                                        latencies.push({
                                            name: displayName,
                                            latency: latencyResult.value
                                        });
                                    }
                                });
                        }
                    });
            });
            
            return Promise.all(promises).then(() => {
                // Sort by performance
                readSpeeds.sort((a, b) => b.speed - a.speed);
                writeSpeeds.sort((a, b) => b.speed - a.speed);
                latencies.sort((a, b) => a.latency - b.latency); // Lower is better for latency
                
                // Take top 5
                const topReadSpeeds = readSpeeds.slice(0, 5);
                const topWriteSpeeds = writeSpeeds.slice(0, 5);
                const topLatencies = latencies.slice(0, 5);
                
                // Create charts
                createBarChart('read-chart', 
                               topReadSpeeds.map(item => item.name), 
                               topReadSpeeds.map(item => item.speed), 
                               'Read Speed (MB/s)');
                
                createBarChart('write-chart', 
                               topWriteSpeeds.map(item => item.name), 
                               topWriteSpeeds.map(item => item.speed), 
                               'Write Speed (MB/s)');
                
                createBarChart('latency-chart', 
                               topLatencies.map(item => item.name), 
                               topLatencies.map(item => item.latency), 
                               'Access Time (ms)');
            });
        })
        .catch(error => console.error('Error fetching data:', error));
    
    // Also get total test count
    fetch('/api/devices')
        .then(response => response.json())
        .then(devices => {
            let testCount = 0;
            
            const promises = devices.map(device => {
                return fetch(`/api/device/${device.device_id}/sessions`)
                    .then(response => response.json())
                    .then(sessions => {
                        testCount += sessions.length;
                    });
            });
            
            return Promise.all(promises).then(() => {
                document.getElementById('test-count').querySelector('.count').textContent = testCount;
            });
        })
        .catch(error => console.error('Error fetching test count:', error));
});

function createBarChart(canvasId, labels, data, label) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: label,
                data: data,
                backgroundColor: 'rgba(54, 162, 235, 0.7)',
                borderColor: 'rgba(54, 162, 235, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}
</script>
{% endblock %}""",
        
        'devices.html': """{% extends 'base.html' %}

{% block title %}Devices - USB Benchmark{% endblock %}

{% block content %}
<div class="devices-list">
    <h2>Tested Devices</h2>
    
    <table class="devices-table">
        <thead>
            <tr>
                <th>Drive</th>
                <th>Model</th>
                <th>Vendor</th>
                <th>Capacity</th>
                <th>Last Tested</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            {% for device in devices %}
            <tr>
                <td>{{ device.drive_letter }}</td>
                <td>{{ device.model or 'Unknown' }}</td>
                <td>{{ device.vendor or 'Unknown' }}</td>
                <td>{{ device.size_gb }} GB</td>
                <td>{{ device.last_seen }}</td>
                <td>
                    <a href="{{ url_for('device_detail', device_id=device.device_id) }}" class="button">View Details</a>
                </td>
            </tr>
            {% else %}
            <tr>
                <td colspan="6" class="no-data">No devices have been tested yet.</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}""",
        
        'device_detail.html': """{% extends 'base.html' %}

{% block title %}{{ device.model or 'Unknown Device' }} - USB Benchmark{% endblock %}

{% block content %}
<div class="device-detail">
    <h2>{{ device.model or 'Unknown Device' }}</h2>
    
    <div class="device-info">
        <div class="info-card">
            <h3>Device Information</h3>
            <table>
                <tr>
                    <th>Drive Letter:</th>
                    <td>{{ device.drive_letter }}</td>
                </tr>
                <tr>
                    <th>Volume Name:</th>
                    <td>{{ device.volume_name or 'No Label' }}</td>
                </tr>
                <tr>
                    <th>Capacity:</th>
                    <td>{{ device.size_gb }} GB</td>
                </tr>
                <tr>
                    <th>Model:</th>
                    <td>{{ device.model or 'Unknown' }}</td>
                </tr>
                <tr>
                    <th>Vendor:</th>
                    <td>{{ device.vendor or 'Unknown' }}</td>
                </tr>
                <tr>
                    <th>Serial Number:</th>
                    <td>{{ device.serial_number or 'Unknown' }}</td>
                </tr>
                <tr>
                    <th>First Tested:</th>
                    <td>{{ device.first_seen }}</td>
                </tr>
                <tr>
                    <th>Last Tested:</th>
                    <td>{{ device.last_seen }}</td>
                </tr>
            </table>
        </div>
    </div>
    
    {% if sessions %}
    <div class="performance-charts">
        <h3>Performance Trends</h3>
        
        <div class="chart-container">
            <div class="chart-card">
                <h4>Read/Write Throughput</h4>
                <canvas id="throughput-chart"></canvas>
            </div>
            
            <div class="chart-card">
                <h4>Latency</h4>
                <canvas id="latency-chart"></canvas>
            </div>
        </div>
    </div>
    
    <div class="benchmark-sessions">
        <h3>Benchmark Sessions</h3>
        
        {% for session in sessions %}
        <div class="session-card">
            <div class="session-header">
                <h4>Test on {{ session.timestamp }}</h4>
                <span class="test-type">{{ session.test_type }} test</span>
            </div>
            
            <div class="results-container">
                <div class="results-category">
                    <h5>Read Performance</h5>
                    <table>
                        {% for result in session.results %}
                            {% if result.category == 'read' and (result.metric.endswith('_avg') or result.metric.endswith('_max')) %}
                            <tr>
                                <th>{{ result.metric | replace('read_', '') | replace('_', ' ') | title }}</th>
                                <td>{{ result.value }} {{ result.unit }}</td>
                            </tr>
                            {% endif %}
                        {% endfor %}
                    </table>
                </div>
                
                <div class="results-category">
                    <h5>Write Performance</h5>
                    <table>
                        {% for result in session.results %}
                            {% if result.category == 'write' and (result.metric.endswith('_avg') or result.metric.endswith('_max')) %}
                            <tr>
                                <th>{{ result.metric | replace('write_', '') | replace('_', ' ') | title }}</th>
                                <td>{{ result.value }} {{ result.unit }}</td>
                            </tr>
                            {% endif %}
                        {% endfor %}
                    </table>
                </div>
                
                <div class="results-category">
                    <h5>Access Time</h5>
                    <table>
                        {% for result in session.results %}
                            {% if result.category == 'seek' and (result.metric.endswith('_avg') or result.metric.endswith('_max')) %}
                            <tr>
                                <th>{{ result.metric | replace('seek_', '') | replace('_', ' ') | title }}</th>
                                <td>{{ result.value }} {{ result.unit }}</td>
                            </tr>
                            {% endif %}
                        {% endfor %}
                    </table>
                </div>
            </div>
        </div>
        {% endfor %}
    </div>
    
    {% else %}
    <div class="no-data">
        <p>No benchmark data available for this device yet.</p>
    </div>
    {% endif %}
</div>
{% endblock %}

{% block scripts %}
{% if sessions %}
<script>
document.addEventListener('DOMContentLoaded', function() {
    // Prepare data for charts
    const timestamps = [];
    const readThroughputs = [];
    const writeThroughputs = [];
    const seekLatencies = [];
    
    {% for session in sessions %}
        timestamps.push('{{ session.timestamp }}');
        
        {% for result in session.results %}
            {% if result.metric == 'read_throughput_avg' %}
                readThroughputs.push({{ result.value }});
            {% endif %}
            {% if result.metric == 'write_throughput_avg' %}
                writeThroughputs.push({{ result.value }});
            {% endif %}
            {% if result.metric == 'seek_latency_avg' %}
                seekLatencies.push({{ result.value }});
            {% endif %}
        {% endfor %}
    {% endfor %}
    
    // Create throughput chart
    const throughputCtx = document.getElementById('throughput-chart').getContext('2d');
    new Chart(throughputCtx, {
        type: 'line',
        data: {
            labels: timestamps.reverse(), // Most recent first in the database query
            datasets: [
                {
                    label: 'Read (MB/s)',
                    data: readThroughputs.reverse(),
                    borderColor: 'rgba(54, 162, 235, 1)',
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                    tension: 0.1
                },
                {
                    label: 'Write (MB/s)',
                    data: writeThroughputs.reverse(),
                    borderColor: 'rgba(255, 99, 132, 1)',
                    backgroundColor: 'rgba(255, 99, 132, 0.2)',
                    tension: 0.1
                }
            ]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Throughput (MB/s)'
                    }
                }
            }
        }
    });
    
    // Create latency chart
    const latencyCtx = document.getElementById('latency-chart').getContext('2d');
    new Chart(latencyCtx, {
        type: 'line',
        data: {
            labels: timestamps.reverse(), // Reverse again since we reversed for the first chart
            datasets: [
                {
                    label: 'Access Time (ms)',
                    data: seekLatencies.reverse(),
                    borderColor: 'rgba(75, 192, 192, 1)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    tension: 0.1
                }
            ]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Latency (ms)'
                    }
                }
            }
        }
    });
});
</script>
{% endif %}
{% endblock %}""",

        'comparison.html': """{% extends 'base.html' %}

{% block title %}Compare Devices - USB Benchmark{% endblock %}

{% block content %}
<div class="comparison">
    <h2>Compare Devices</h2>
    
    <form method="post" class="comparison-form">
        <div class="form-group">
            <label for="devices">Select devices to compare:</label>
            <select name="devices" id="devices" multiple required>
                {% for device in devices %}
                <option value="{{ device.device_id }}" {% if device.device_id in selected_devices %}selected{% endif %}>
                    {{ device.model or 'Unknown' }} ({{ device.drive_letter }}) - {{ device.size_gb }}GB
                </option>
                {% endfor %}
            </select>
            <p class="help-text">Hold Ctrl (or Cmd on Mac) to select multiple devices</p>
        </div>
        
        <button type="submit" class="button">Compare</button>
    </form>
    
    {% if comparison_data %}
    <div class="comparison-results">
        <h3>Comparison Results</h3>
        
        <div class="chart-container">
            <div class="chart-card">
                <h4>Read Throughput</h4>
                <canvas id="read-comparison-chart"></canvas>
            </div>
            
            <div class="chart-card">
                <h4>Write Throughput</h4>
                <canvas id="write-comparison-chart"></canvas>
            </div>
        </div>
        
        <div class="chart-container">
            <div class="chart-card">
                <h4>Access Time (Seek Latency)</h4>
                <canvas id="latency-comparison-chart"></canvas>
            </div>
        </div>
        
        <div class="comparison-table">
            <h4>Detailed Comparison</h4>
            <table>
                <thead>
                    <tr>
                        <th>Metric</th>
                        {% for device_id in selected_devices %}
                        <th>{{ comparison_data[device_id].info.model or 'Unknown' }} ({{ comparison_data[device_id].info.drive_letter }})</th>
                        {% endfor %}
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>Capacity</strong></td>
                        {% for device_id in selected_devices %}
                        <td>{{ comparison_data[device_id].info.size_gb }} GB</td>
                        {% endfor %}
                    </tr>
                    
                    <tr>
                        <td><strong>Vendor</strong></td>
                        {% for device_id in selected_devices %}
                        <td>{{ comparison_data[device_id].info.vendor or 'Unknown' }}</td>
                        {% endfor %}
                    </tr>
                    
                    <tr class="section-header">
                        <td colspan="{{ selected_devices|length + 1 }}">Read Performance</td>
                    </tr>
                    
                    <tr>
                        <td>Read Throughput (Avg)</td>
                        {% for device_id in selected_devices %}
                        <td>{{ comparison_data[device_id].results.read.read_throughput_avg.value }} {{ comparison_data[device_id].results.read.read_throughput_avg.unit }}</td>
                        {% endfor %}
                    </tr>
                    
                    <tr>
                        <td>Read Throughput (Max)</td>
                        {% for device_id in selected_devices %}
                        <td>{{ comparison_data[device_id].results.read.read_throughput_max.value }} {{ comparison_data[device_id].results.read.read_throughput_max.unit }}</td>
                        {% endfor %}
                    </tr>
                    
                    <tr>
                        <td>Read Latency (Avg)</td>
                        {% for device_id in selected_devices %}
                        <td>{{ comparison_data[device_id].results.read.read_latency_avg.value }} {{ comparison_data[device_id].results.read.read_latency_avg.unit }}</td>
                        {% endfor %}
                    </tr>
                    
                    <tr class="section-header">
                        <td colspan="{{ selected_devices|length + 1 }}">Write Performance</td>
                    </tr>
                    
                    <tr>
                        <td>Write Throughput (Avg)</td>
                        {% for device_id in selected_devices %}
                        <td>{{ comparison_data[device_id].results.write.write_throughput_avg.value }} {{ comparison_data[device_id].results.write.write_throughput_avg.unit }}</td>
                        {% endfor %}
                    </tr>
                    
                    <tr>
                        <td>Write Throughput (Max)</td>
                        {% for device_id in selected_devices %}
                        <td>{{ comparison_data[device_id].results.write.write_throughput_max.value }} {{ comparison_data[device_id].results.write.write_throughput_max.unit }}</td>
                        {% endfor %}
                    </tr>
                    
                    <tr>
                        <td>Write Latency (Avg)</td>
                        {% for device_id in selected_devices %}
                        <td>{{ comparison_data[device_id].results.write.write_latency_avg.value }} {{ comparison_data[device_id].results.write.write_latency_avg.unit }}</td>
                        {% endfor %}
                    </tr>
                    
                    <tr class="section-header">
                        <td colspan="{{ selected_devices|length + 1 }}">Access Time</td>
                    </tr>
                    
                    <tr>
                        <td>Seek Latency (Avg)</td>
                        {% for device_id in selected_devices %}
                        <td>{{ comparison_data[device_id].results.seek.seek_latency_avg.value }} {{ comparison_data[device_id].results.seek.seek_latency_avg.unit }}</td>
                        {% endfor %}
                    </tr>
                    
                    <tr>
                        <td>Seek Latency (Min)</td>
                        {% for device_id in selected_devices %}
                        <td>{{ comparison_data[device_id].results.seek.seek_latency_min.value }} {{ comparison_data[device_id].results.seek.seek_latency_min.unit }}</td>
                        {% endfor %}
                    </tr>
                    
                    <tr>
                        <td>Seek Latency (Max)</td>
                        {% for device_id in selected_devices %}
                        <td>{{ comparison_data[device_id].results.seek.seek_latency_max.value }} {{ comparison_data[device_id].results.seek.seek_latency_max.unit }}</td>
                        {% endfor %}
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
    {% endif %}
</div>
{% endblock %}

{% block scripts %}
{% if comparison_data %}
<script>
document.addEventListener('DOMContentLoaded', function() {
    // Prepare data for charts
    const devices = [];
    const readThroughputs = [];
    const writeThroughputs = [];
    const seekLatencies = [];
    
    {% for device_id in selected_devices %}
    devices.push('{{ comparison_data[device_id].info.model or "Unknown" }} ({{ comparison_data[device_id].info.drive_letter }})');
    readThroughputs.push({{ comparison_data[device_id].results.read.read_throughput_avg.value }});
    writeThroughputs.push({{ comparison_data[device_id].results.write.write_throughput_avg.value }});
    seekLatencies.push({{ comparison_data[device_id].results.seek.seek_latency_avg.value }});
    {% endfor %}
    
    // Create read throughput chart
    createBarChart('read-comparison-chart', devices, readThroughputs, 'Read Throughput (MB/s)');
    
    // Create write throughput chart
    createBarChart('write-comparison-chart', devices, writeThroughputs, 'Write Throughput (MB/s)');
    
    // Create latency chart
    createBarChart('latency-comparison-chart', devices, seekLatencies, 'Access Time (ms)');
});

function createBarChart(canvasId, labels, data, label) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: label,
                data: data,
                backgroundColor: 'rgba(54, 162, 235, 0.7)',
                borderColor: 'rgba(54, 162, 235, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}
</script>
{% endif %}
{% endblock %}"""
    }
    
    # Create CSS
    css = """/* Main Styles */
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.6;
    color: #333;
    margin: 0;
    padding: 0;
    background-color: #f5f5f5;
}

header {
    background-color: #2c3e50;
    color: white;
    padding: 1rem;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
}

header h1 {
    margin: 0;
    font-size: 1.8rem;
}

nav ul {
    list-style: none;
    padding: 0;
    margin: 1rem 0 0 0;
    display: flex;
}

nav li {
    margin-right: 1.5rem;
}

nav a {
    color: white;
    text-decoration: none;
    font-weight: 500;
    padding: 0.5rem 0;
    border-bottom: 2px solid transparent;
    transition: border-color 0.3s;
}

nav a:hover {
    border-color: white;
}

main {
    max-width: 1200px;
    margin: 0 auto;
    padding: 2rem;
}

footer {
    background-color: #2c3e50;
    color: white;
    text-align: center;
    padding: 1rem;
    margin-top: 2rem;
}

/* Dashboard */
.dashboard-summary {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 1.5rem;
    margin-bottom: 2rem;
}

.summary-card {
    background-color: white;
    border-radius: 8px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    padding: 1.5rem;
    text-align: center;
}

.summary-card h3 {
    margin-top: 0;
    color: #2c3e50;
    font-size: 1.2rem;
}

.summary-card .count {
    font-size: 2.5rem;
    font-weight: bold;
    color: #3498db;
    margin: 0.5rem 0;
}

.chart-container {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
    gap: 1.5rem;
    margin-bottom: 2rem;
}

.chart-card {
    background-color: white;
    border-radius: 8px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    padding: 1.5rem;
}

.chart-card h3, .chart-card h4 {
    margin-top: 0;
    color: #2c3e50;
}

/* Device List */
.devices-table {
    width: 100%;
    border-collapse: collapse;
    background-color: white;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    border-radius: 8px;
    overflow: hidden;
}

.devices-table th, .devices-table td {
    padding: 1rem;
    text-align: left;
    border-bottom: 1px solid #eee;
}

.devices-table th {
    background-color: #f9f9f9;
    font-weight: 600;
}

.devices-table tr:last-child td {
    border-bottom: none;
}

.button {
    display: inline-block;
    background-color: #3498db;
    color: white;
    padding: 0.5rem 1rem;
    border-radius: 4px;
    text-decoration: none;
    font-weight: 500;
    transition: background-color 0.3s;
}

.button:hover {
    background-color: #2980b9;
}

.no-data {
    text-align: center;
    padding: 2rem;
    color: #7f8c8d;
}

/* Device Detail */
.device-info {
    margin-bottom: 2rem;
}

.info-card {
    background-color: white;
    border-radius: 8px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    padding: 1.5rem;
}

.info-card h3 {
    margin-top: 0;
    color: #2c3e50;
    border-bottom: 1px solid #eee;
    padding-bottom: 0.5rem;
}

.info-card table {
    width: 100%;
}

.info-card th, .info-card td {
    padding: 0.5rem;
    text-align: left;
}

.info-card th {
    width: 35%;
    color: #7f8c8d;
    font-weight: 600;
}

.session-card {
    background-color: white;
    border-radius: 8px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    padding: 1.5rem;
    margin-bottom: 1.5rem;
}

.session-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
    border-bottom: 1px solid #eee;
    padding-bottom: 0.5rem;
}

.session-header h4 {
    margin: 0;
    color: #2c3e50;
}

.test-type {
    background-color: #3498db;
    color: white;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.9rem;
}

.results-container {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 1.5rem;
}

.results-category h5 {
    margin-top: 0;
    color: #2c3e50;
    border-bottom: 1px solid #eee;
    padding-bottom: 0.5rem;
}

.results-category table {
    width: 100%;
}

.results-category th, .results-category td {
    padding: 0.5rem;
    text-align: left;
}

.results-category th {
    color: #7f8c8d;
    font-weight: 600;
}

/* Comparison */
.comparison-form {
    background-color: white;
    border-radius: 8px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    padding: 1.5rem;
    margin-bottom: 2rem;
}

.form-group {
    margin-bottom: 1rem;
}

.form-group label {
    display: block;
    margin-bottom: 0.5rem;
    font-weight: 600;
    color: #2c3e50;
}

.form-group select {
    width: 100%;
    padding: 0.5rem;
    border: 1px solid #ddd;
    border-radius: 4px;
    min-height: 150px;
}

.help-text {
    font-size: 0.9rem;
    color: #7f8c8d;
    margin-top: 0.5rem;
}

.comparison-table table {
    width: 100%;
    border-collapse: collapse;
    background-color: white;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    border-radius: 8px;
    overflow: hidden;
    margin-top: 1.5rem;
}

.comparison-table th, .comparison-table td {
    padding: 1rem;
    text-align: left;
    border-bottom: 1px solid #eee;
}

.comparison-table th {
    background-color: #f9f9f9;
    font-weight: 600;
}

.section-header {
    background-color: #f1f1f1;
    font-weight: bold;
    text-align: center;
}"""
    
    # Create directory and write files
    for template_name, content in templates.items():
        template_path = os.path.join(templates_dir, template_name)
        with open(template_path, 'w') as f:
            f.write(content)
    
    # Write CSS
    css_path = os.path.join(static_dir, 'css', 'style.css')
    with open(css_path, 'w') as f:
        f.write(css)

if __name__ == '__main__':
    # Create template files
    create_templates()
    
    # Run Flask app
    app.run(debug=True)