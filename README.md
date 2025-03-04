# USB Flash Drive Benchmark Tool

A comprehensive tool for benchmarking USB flash drives on Windows, with HTML report generation and device comparison.

## Features

- Measures read and write performance for both latency and throughput
- Tests random seek performance to simulate real-world usage
- Generates detailed HTML reports with charts and tables
- Supports comparing multiple devices in a single report
- Creates JSON data for programmatic access
- Uses caching mitigation techniques for more accurate results

## Requirements

- Windows OS
- Python 3.6+
- Required packages (install via `pip install -r requirements.txt`):
  - pywin32 (for direct disk I/O)
  - WMI (for device detection)
  - beautifulsoup4 (for HTML report parsing)

## Installation

1. Clone or download this repository
2. Install required packages:
   ```
   pip install -r requirements.txt
   ```

## Usage

Run the main script:

```
python main.py
```

The tool will:
1. Detect and list available USB flash drives
2. Let you select a drive to test
3. Offer test customization options (quick, standard, thorough, or custom)
4. Run the selected benchmarks
5. Display results in the console
6. Generate an HTML report (optional)

## Test Types

- **Quick Test**: Fast assessment (~1-2 minutes)
- **Standard Test**: Balanced approach (~2-3 minutes) - recommended
- **Thorough Test**: Detailed assessment (~5-8 minutes)
- **Advanced**: Customize each test parameter

## File Structure

- `main.py` - Main script and entry point
- `utils.py` - Utility functions (drive detection, cache clearing)
- `benchmark.py` - Core benchmark functions
- `report.py` - HTML report generation
- `requirements.txt` - Required Python packages

## HTML Reports

The tool can generate detailed HTML reports that include:
- Interactive bar charts for latency and throughput comparisons
- Summary table with key metrics
- Detailed device information sections
- Support for multiple devices in a single report

Reports are saved as `usb_benchmark_report.html` in the same directory as the script.

## JSON Data

Raw benchmark data is also saved as `usb_benchmark_data.json` for programmatic access.

## Notes

- For the most accurate read throughput tests, the tool requires pywin32 and administrator privileges.
- The tool uses multiple techniques to mitigate filesystem caching.
- If you're comparing multiple devices, make sure to run the same test type for all devices.

## License

MIT