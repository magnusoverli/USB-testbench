"""
USB Flash Drive Benchmark Tool

This tool benchmarks USB flash drives for read/write performance and latency.
"""
import os
import time
import webbrowser
from typing import Dict, Any

# Import modules
from utils import get_usb_drives, select_drive, clear_cache, display_results, HAS_WIN32
from benchmark import write_benchmark, read_benchmark, random_seek_benchmark
from report import (
    parse_existing_report, 
    device_exists, 
    convert_benchmarks_to_device_data, 
    generate_html_report,
    save_json_data
)

def main():
    """Main function for the USB flash drive benchmark tool."""
    print("USB Flash Drive Benchmark Tool")
    print("-----------------------------")
    
    # Check for PyWin32 at startup
    if not HAS_WIN32:
        print("\nNOTICE: PyWin32 is not installed. For more accurate read throughput tests,")
        print("install it using: pip install pywin32")
        print("The benchmark will continue without it, but read speeds may be less accurate.\n")
    
    # Get USB drives
    drives = get_usb_drives()
    
    if not drives:
        print("No USB flash drives found!")
        return
    
    # Let the user select a drive
    selected_drive = select_drive(drives)
    drive_path = selected_drive['DriveLetter']
    
    print(f"\nSelected drive: {drive_path} ({selected_drive.get('Model', 'Unknown Model')})")
    confirmation = input("Continue with benchmark? This will create and delete files on the selected drive. (y/n): ")
    
    if confirmation.lower() != 'y':
        print("Benchmark cancelled.")
        return
    
    # Ask for test customization
    print("\nCustomize benchmark tests:")
    print("1. Quick test (fast, basic assessment)")
    print("2. Standard test (recommended balance)")
    print("3. Thorough test (detailed, longer duration)")
    print("4. Advanced (customize each test)")
    
    test_choice = "2"  # Default to standard test
    try:
        test_choice = input("Select test type [2]: ").strip() or "2"
    except:
        pass
    
    # Set test parameters based on choice
    if test_choice == "1":  # Quick
        print("\nRunning quick test (approx. 1-2 minutes)...")
        latency_test = True
        throughput_test = True
        latency_file_count = 15
        throughput_file_size_mb = 20
        seek_count = 20
    elif test_choice == "2":  # Standard
        print("\nRunning standard test (approx. 2-3 minutes)...")
        latency_test = True
        throughput_test = True
        latency_file_count = 25
        throughput_file_size_mb = 25
        seek_count = 50
    elif test_choice == "3":  # Thorough
        print("\nRunning thorough test (approx. 5-8 minutes)...")
        latency_test = True
        throughput_test = True
        latency_file_count = 50
        throughput_file_size_mb = 50
        seek_count = 100
    elif test_choice == "4":  # Advanced
        try:
            latency_test = input("Run latency tests? (y/n) [y]: ").strip().lower() != "n"
            throughput_test = input("Run throughput tests? (y/n) [y]: ").strip().lower() != "n"
            
            latency_file_count_input = input("Number of files for latency test [25]: ").strip()
            latency_file_count = int(latency_file_count_input) if latency_file_count_input else 25
            
            throughput_file_size_input = input("Size in MB for throughput test files [25]: ").strip()
            throughput_file_size_mb = int(throughput_file_size_input) if throughput_file_size_input else 25
            
            seek_count_input = input("Number of random seeks [50]: ").strip()
            seek_count = int(seek_count_input) if seek_count_input else 50
            
            print(f"\nRunning custom test with {latency_file_count} latency files, " 
                  f"{throughput_file_size_mb}MB throughput files, and {seek_count} seeks...")
        except ValueError:
            print("Invalid input. Using standard test values.")
            latency_test = True
            throughput_test = True
            latency_file_count = 25
            throughput_file_size_mb = 25
            seek_count = 50
    else:
        print("Invalid choice. Using standard test.")
        latency_test = True
        throughput_test = True
        latency_file_count = 25
        throughput_file_size_mb = 25
        seek_count = 50
    
    print("\nStarting benchmark tests...")
    start_time = time.time()
    
    # Perform benchmarks
    try:
        # Force a single cache clear before starting tests
        print("Preparing system (clearing caches)...")
        clear_cache()
        
        # Run benchmarks
        write_results = write_benchmark(
            drive_path, 
            test_latency=latency_test, 
            test_throughput=throughput_test,
            latency_file_count=latency_file_count,
            throughput_file_size_mb=throughput_file_size_mb
        )
        
        read_results = read_benchmark(
            drive_path, 
            test_latency=latency_test, 
            test_throughput=throughput_test,
            latency_file_count=latency_file_count,
            throughput_file_size_mb=throughput_file_size_mb
        )
        
        seek_results = random_seek_benchmark(
            drive_path, 
            num_seeks=seek_count,
            file_size_mb=min(throughput_file_size_mb * 2, 100)  # Scale file size based on test type
        )
        
        # Display total test time
        total_time = time.time() - start_time
        minutes, seconds = divmod(int(total_time), 60)
        print(f"\nBenchmark completed in {minutes} minutes, {seconds} seconds.")
        
        # Display results
        display_results(selected_drive, write_results, read_results, seek_results)
        
        # Add a note if PyWin32 is not installed
        if throughput_test and not HAS_WIN32:
            print("\nNOTE: For more accurate read throughput tests, install PyWin32:")
            print("      pip install pywin32")
            
        # Generate HTML report
        print("\nWould you like to save the benchmark results to an HTML report?")
        save_report = input("This will create or update usb_benchmark_report.html (y/n) [y]: ").strip().lower() != 'n'
        
        if save_report:
            try:
                # Generate a device data object from benchmark results
                device_data = convert_benchmarks_to_device_data(selected_drive, write_results, read_results, seek_results)
                
                # Define the report paths (same directory as script)
                script_dir = os.path.dirname(os.path.abspath(__file__))
                html_report_path = os.path.join(script_dir, "usb_benchmark_report.html")
                json_data_path = os.path.join(script_dir, "usb_benchmark_data.json")
                
                # Check if the report already exists
                existing_devices = parse_existing_report(html_report_path)
                device_index = device_exists(existing_devices, device_data)
                
                if device_index >= 0:
                    print(f"\nThis device '{device_data['device']['friendly_name']}' already exists in the report.")
                    replace = input("Do you want to replace the existing results? (y/n) [n]: ").strip().lower() == 'y'
                    
                    if replace:
                        print("Replacing existing results...")
                        existing_devices[device_index] = device_data
                    else:
                        print("Keeping existing results. New data will not be added to the report.")
                else:
                    print(f"\nAdding new device '{device_data['device']['friendly_name']}' to the report.")
                    existing_devices.append(device_data)
                
                # Generate the HTML report with updated data
                generate_html_report(existing_devices, html_report_path)
                
                # Save as JSON for programmatic access
                save_json_data(existing_devices, json_data_path)
                
                print(f"\nBenchmark report saved to: {html_report_path}")
                print(f"Benchmark data saved to: {json_data_path}")
                
                # Try to open the report in the default browser
                try:
                    open_report = input("Would you like to open the report now? (y/n) [y]: ").strip().lower() != 'n'
                    if open_report:
                        webbrowser.open('file://' + os.path.abspath(html_report_path))
                except Exception as e:
                    print(f"Could not open browser: {e}")
                    
            except Exception as e:
                print(f"Error saving benchmark report: {e}")
                print("Make sure you have beautifulsoup4 installed: pip install beautifulsoup4")
                
    except Exception as e:
        print(f"Error during benchmark: {e}")
        print("Benchmark failed. Please check if the drive is still connected and has sufficient space.")

if __name__ == "__main__":
    main()