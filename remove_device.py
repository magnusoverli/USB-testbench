#!/usr/bin/env python3
"""
Simple script to handle device removal requests from the HTML report.
"""
import os
import sys
import cgi
import cgitb
from pathlib import Path

# Enable detailed error reporting
cgitb.enable()

# Add parent directory to path to import report module
sys.path.append(str(Path(__file__).parent))
from report import remove_device_from_report

def main():
    """Handle device removal request."""
    # Print headers for CGI response
    print("Content-Type: text/html")
    print()
    
    # Get form data
    form = cgi.FieldStorage()
    device_id = int(form.getvalue("device_id", -1))
    script_path = form.getvalue("script_path", "")
    
    # Get the directory where the report is located
    report_dir = os.path.dirname(os.path.abspath(__file__))
    report_path = os.path.join(report_dir, "usb_benchmark_report.html")
    json_path = os.path.join(report_dir, "usb_benchmark_data.json")
    
    # Remove the device
    success = remove_device_from_report(report_path, json_path, device_id)
    
    # Redirect back to the report
    redirect_path = script_path if script_path else f"file://{report_path}"
    
    # Output HTML with redirect
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="refresh" content="1;url={redirect_path}">
    <title>{'Device Removed' if success else 'Error'}</title>
</head>
<body>
    <h2>{'Device successfully removed!' if success else 'Error removing device'}</h2>
    <p>Redirecting back to the report...</p>
</body>
</html>
"""
    print(html)

if __name__ == "__main__":
    main()