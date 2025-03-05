"""
USB Flash Drive Benchmark Tool

This tool benchmarks USB flash drives for read/write performance and latency.
"""
import os
import sys
import time
from typing import Dict, Any

# Import modules
from utils import get_usb_drives, select_drive, clear_cache, display_results, HAS_WIN32
from benchmark import write_benchmark, read_benchmark, random_seek_benchmark
import db

def main():
    """Main function for the USB flash drive benchmark tool."""
    print("USB Flash Drive Benchmark Tool")
    print("-----------------------------")
    
    # Initialize database
    try:
        db.init_database()
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Warning: Could not initialize database: {e}")
        print("Results will not be saved to database.")
        has_db = False
    else:
        has_db = True
    
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
    device_id = selected_drive['device_id']
    
    print(f"\nSelected drive: {drive_path} ({selected_drive.get('Model', 'Unknown Model')})")
    print(f"Device ID: {device_id}")
    
    # Show device history if available in the database
    if has_db:
        try:
            history = db.get_device_history(device_id)
            if history:
                print(f"\nFound {len(history)} previous benchmark sessions for this device")
                print(f"Last tested: {history[0]['timestamp']}")
        except Exception as e:
            print(f"Could not retrieve device history: {e}")
    
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
        test_type = "quick"
        latency_test = True
        throughput_test = True
        latency_file_count = 15
        throughput_file_size_mb = 20
        seek_count = 20
    elif test_choice == "2":  # Standard
        print("\nRunning standard test (approx. 2-3 minutes)...")
        test_type = "standard"
        latency_test = True
        throughput_test = True
        latency_file_count = 25
        throughput_file_size_mb = 25
        seek_count = 50
    elif test_choice == "3":  # Thorough
        print("\nRunning thorough test (approx. 5-8 minutes)...")
        test_type = "thorough"
        latency_test = True
        throughput_test = True
        latency_file_count = 50
        throughput_file_size_mb = 50
        seek_count = 100
    elif test_choice == "4":  # Advanced
        test_type = "custom"
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
        test_type = "standard"
        latency_test = True
        throughput_test = True
        latency_file_count = 25
        throughput_file_size_mb = 25
        seek_count = 50
    
    # Store test parameters for database
    test_params = {
        "write_latency_file_count": latency_file_count if latency_test else 0,
        "write_throughput_file_size_mb": throughput_file_size_mb if throughput_test else 0,
        "read_latency_file_count": latency_file_count if latency_test else 0,
        "read_throughput_file_size_mb": throughput_file_size_mb if throughput_test else 0,
        "seek_count": seek_count
    }
    
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
        
        # Save results to database if available
        if has_db:
            try:
                # First save or update device info
                db.save_device_info(selected_drive)
                
                # Then save benchmark results
                session_id = db.save_benchmark_results(
                    device_id, 
                    test_type,
                    test_params,
                    write_results, 
                    read_results, 
                    seek_results
                )
                
                print(f"\nResults saved to database (Session ID: {session_id})")
                
                # Offer to export results
                export_choice = input("\nExport results to file? (y/n): ").lower()
                if export_choice == 'y':
                    format_choice = input("Export format (json/csv) [json]: ").lower() or 'json'
                    if format_choice not in ['json', 'csv']:
                        print("Invalid format. Using JSON.")
                        format_choice = 'json'
                    
                    try:
                        export_path = db.export_device_history(device_id, format_choice)
                        print(f"Results exported to: {export_path}")
                    except Exception as e:
                        print(f"Export failed: {e}")
                
            except Exception as e:
                print(f"\nWarning: Could not save results to database: {e}")
        
    except Exception as e:
        print(f"Error during benchmark: {e}")
        print("Benchmark failed. Please check if the drive is still connected and has sufficient space.")

if __name__ == "__main__":
    main()