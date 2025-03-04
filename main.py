import os
import random
import time
import subprocess
import tempfile
import shutil
import json
import statistics
import ctypes
import struct
import re
import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# Add Win32 API imports for direct disk access (bypassing cache)
try:
    import win32file
    import win32con
    HAS_WIN32 = True
except ImportError:
    print("Warning: PyWin32 module not found. Installing it will improve benchmark accuracy.")
    print("Run: pip install pywin32")
    HAS_WIN32 = False

def get_usb_drives() -> List[Dict]:
    """Get a list of connected USB flash drives using PowerShell."""
    # PowerShell command to get USB drives that are removable (flash drives)
    ps_command = """
    Get-WmiObject Win32_DiskDrive | 
    Where-Object { $_.InterfaceType -eq "USB" -and $_.MediaType -like "*removable*" } | 
    ForEach-Object {
        $disk = $_
        $partitions = Get-WmiObject -Query "ASSOCIATORS OF {Win32_DiskDrive.DeviceID='$($disk.DeviceID)'} WHERE AssocClass=Win32_DiskDriveToDiskPartition"
        
        foreach($partition in $partitions) {
            $volumes = Get-WmiObject -Query "ASSOCIATORS OF {Win32_DiskPartition.DeviceID='$($partition.DeviceID)'} WHERE AssocClass=Win32_LogicalDiskToPartition"
            
            foreach($volume in $volumes) {
                New-Object PSObject -Property @{
                    DriveLetter = $volume.DeviceID
                    VolumeName = $volume.VolumeName
                    SizeGB = [math]::Round($volume.Size / 1GB, 2)
                    Model = $disk.Model
                    Vendor = $disk.Manufacturer
                    SerialNumber = $disk.SerialNumber
                    InterfaceType = $disk.InterfaceType
                    MediaType = $disk.MediaType
                }
            }
        }
    } | ConvertTo-Json
    """
    
    # Execute PowerShell command and capture output
    process = subprocess.run(
        ["powershell", "-Command", ps_command],
        capture_output=True,
        text=True
    )
    
    if process.returncode != 0:
        print(f"Error getting USB drives: {process.stderr}")
        return []
    
    # Parse JSON output
    try:
        if not process.stdout.strip():
            return []
        result = json.loads(process.stdout)
        # Handle case where only one drive is returned (not in a list)
        if isinstance(result, dict):
            return [result]
        return result
    except json.JSONDecodeError:
        print(f"Error parsing JSON output: {process.stdout}")
        return []

def select_drive(drives: List[Dict]) -> Dict:
    """Let the user select a drive from the list."""
    if not drives:
        print("No USB flash drives found!")
        exit(1)
    
    print("\nAvailable USB flash drives:")
    for i, drive in enumerate(drives):
        vendor = drive.get('Vendor', 'Unknown Vendor')
        model = drive.get('Model', 'Unknown Model')
        volume_name = drive.get('VolumeName', 'No Label')
        
        print(f"{i+1}. {drive['DriveLetter']} - {volume_name} ({drive['SizeGB']} GB)")
        print(f"   Model: {model} | Vendor: {vendor}")
    
    while True:
        try:
            selection = int(input("\nSelect a drive (number): ")) - 1
            if 0 <= selection < len(drives):
                return drives[selection]
            else:
                print("Invalid selection. Please try again.")
        except ValueError:
            print("Please enter a number.")

def clear_cache():
    """
    Attempt to clear filesystem cache using multiple methods.
    This is a lighter version of the cache clearing for faster benchmarks.
    """
    try:
        # Try to use Windows API to directly flush file system cache
        if HAS_WIN32:
            try:
                # Use NtSetSystemInformation function to flush filesystem cache
                # This requires administrator privileges
                system_flush_code = 40  # SystemCacheInformation
                cache_command = 1       # EmptyCache
                
                # Attempt to flush the cache
                # This won't work without admin rights but it's safe to try
                fn = ctypes.windll.ntdll.NtSetSystemInformation
                zero_struct = ctypes.c_ubyte * 4
                zero_val = zero_struct(0, 0, 0, cache_command)
                fn(system_flush_code, ctypes.byref(zero_val), ctypes.sizeof(zero_val))
            except Exception:
                # Don't print an error - this is expected to fail without admin rights
                pass
        
        # Method 1: Create and read a temporary file to push other content out of cache
        temp_size_mb = 50  # Reduced from 200MB for faster operation
        temp_data = os.urandom(temp_size_mb * 1024 * 1024)
        
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file_path = temp_file.name
            temp_file.write(temp_data)
            temp_file.flush()
            os.fsync(temp_file.fileno())  # Force write to disk
        
        # Read the file to push other content out of cache
        with open(temp_file_path, 'rb') as temp_file:
            _ = temp_file.read()
        
        # Delete the temporary file
        os.unlink(temp_file_path)
        
        # Method 2: Allocate and release a smaller array to clear memory caches
        large_array = bytearray(100 * 1024 * 1024)  # Reduced from 500MB to 100MB
        # Fill with random data to prevent optimization - using bigger steps for speed
        for i in range(0, len(large_array), 10 * 1024 * 1024):  # 10MB chunks instead of 1MB
            end = min(i + 10 * 1024 * 1024, len(large_array))
            large_array[i:end] = os.urandom(end - i)
        # Release the array
        del large_array
        
    except Exception as e:
        print(f"Warning: Cache clearing may not be fully effective: {e}")
    
    # Force garbage collection
    import gc
    gc.collect()
    
    # Shorter sleep time
    time.sleep(0.25)  # Reduced from 1s to 0.25s

def write_benchmark(drive_path: str, num_files: int = 10, file_size_mb: int = 10, 
                 test_latency: bool = True, test_throughput: bool = True,
                 latency_file_count: int = 50, throughput_file_size_mb: int = 50) -> Dict:
    """
    Perform write benchmark test.
    
    Args:
        drive_path: Path to the drive
        num_files: Number of files to write
        file_size_mb: Size of each file in MB
        test_latency: Whether to run small file latency tests
        test_throughput: Whether to run large file throughput tests
        latency_file_count: Number of small files for latency test
        throughput_file_size_mb: Size of each file for throughput test
        
    Returns:
        Dictionary with benchmark results
    """
    results = {}
    
    # Latency-optimized test (small files, many operations)
    if test_latency:
        print(f"\nPerforming write LATENCY benchmark on {drive_path}...")
        
        # Create a benchmark directory with unique name to avoid caching
        timestamp = int(time.time())
        benchmark_dir = os.path.join(drive_path, f"benchmark_test_lat_{timestamp}")
        if os.path.exists(benchmark_dir):
            shutil.rmtree(benchmark_dir)
        os.makedirs(benchmark_dir)
        
        latency_file_size_kb = 4  # Small 4KB files for latency testing
        latencies = []
        
        print(f"Writing {latency_file_count} small files ({latency_file_size_kb}KB each)...")
        
        # Only clear cache once before the batch for quick tests
        if latency_file_count <= 20:
            clear_cache()
            
        for i in range(latency_file_count):
            # Update progress bar
            progress = (i + 1) / latency_file_count * 100
            bar_length = 30
            filled_length = int(bar_length * (i + 1) // latency_file_count)
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            print(f"\rProgress: [{bar}] {progress:.1f}%", end='')
            
            # Generate new random data for each file
            data = os.urandom(latency_file_size_kb * 1024)
            
            # Create a unique filename
            file_path = os.path.join(benchmark_dir, f"test_lat_{i}_{timestamp}.bin")
            
            # Clear cache only periodically for larger tests
            if latency_file_count > 20 and i % 5 == 0:
                clear_cache()
            
            # Time the write operation
            start_time = time.time()
            with open(file_path, 'wb') as f:
                f.write(data)
                # Ensure data is written to disk
                f.flush()
                os.fsync(f.fileno())
            
            end_time = time.time()
            
            duration = end_time - start_time
            latencies.append(duration)
        
        print("\nLatency test completed.")
        
        # Clean up
        shutil.rmtree(benchmark_dir)
        
        results.update({
            "write_latency_avg": statistics.mean(latencies),
            "write_latency_min": min(latencies),
            "write_latency_max": max(latencies),
            "write_latency_median": statistics.median(latencies),
            "write_latency_file_size_kb": latency_file_size_kb,
            "write_latency_file_count": latency_file_count
        })
    
    # Throughput-optimized test (large files, fewer operations)
    if test_throughput:
        print(f"\nPerforming write THROUGHPUT benchmark on {drive_path}...")
        
        # Create a benchmark directory with unique name to avoid caching
        timestamp = int(time.time())
        benchmark_dir = os.path.join(drive_path, f"benchmark_test_thr_{timestamp}")
        if os.path.exists(benchmark_dir):
            shutil.rmtree(benchmark_dir)
        os.makedirs(benchmark_dir)
        
        throughput_file_count = min(3, num_files)  # Fewer operations for throughput
        throughputs = []
        
        for i in range(throughput_file_count):
            print(f"\nWriting large file {i+1}/{throughput_file_count} ({throughput_file_size_mb}MB)...")
            
            # Generate new random data for each file to defeat compression
            data = os.urandom(throughput_file_size_mb * 1024 * 1024)
            
            # Create a unique filename
            file_path = os.path.join(benchmark_dir, f"test_thr_{i}_{timestamp}.bin")
            
            # Clear cache before each test
            clear_cache()
            
            # Time the write operation
            start_time = time.time()
            with open(file_path, 'wb') as f:
                f.write(data)
                # Ensure data is written to disk
                f.flush()
                os.fsync(f.fileno())
            
            end_time = time.time()
            
            duration = end_time - start_time
            
            # Calculate throughput in MB/s
            throughput = throughput_file_size_mb / duration
            throughputs.append(throughput)
            
            print(f"File {i+1}: Write throughput: {throughput:.2f} MB/s ({duration:.2f}s)")
        
        # Clean up
        shutil.rmtree(benchmark_dir)
        
        results.update({
            "write_throughput_avg": statistics.mean(throughputs),
            "write_throughput_min": min(throughputs),
            "write_throughput_max": max(throughputs),
            "write_throughput_file_size_mb": throughput_file_size_mb,
            "write_throughput_file_count": throughput_file_count
        })
    
    return results

def read_with_no_buffering(file_path: str, file_size_bytes: int) -> (float, float):
    """
    Read a file with Windows cache disabled using direct I/O.
    
    Args:
        file_path: Path to the file to read
        file_size_bytes: Size of the file in bytes
        
    Returns:
        Tuple of (duration in seconds, throughput in MB/s)
    """
    # Standard reading fallback
    def standard_reading():
        start_time = time.time()
        with open(file_path, 'rb') as f:
            # Read in chunks to avoid loading entire file into memory
            chunk_size = 4 * 1024 * 1024  # 4MB chunks
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
        end_time = time.time()
        duration = end_time - start_time
        throughput = file_size_bytes / (1024 * 1024) / duration
        return duration, throughput
    
    # If PyWin32 is not available, use standard reading
    if not HAS_WIN32:
        return standard_reading()
    
    # Try to use direct I/O with PyWin32
    try:
        # Sector size is typically 4KB for USB drives
        sector_size = 4096
        buffer_size = 1024 * 1024  # 1MB buffer
        # Align buffer to sector size
        buffer_size = (buffer_size // sector_size) * sector_size
        
        # Open with NO_BUFFERING flag to bypass cache
        handle = win32file.CreateFile(
            file_path,
            win32file.GENERIC_READ,
            win32file.FILE_SHARE_READ,
            None,
            win32file.OPEN_EXISTING,
            win32file.FILE_FLAG_NO_BUFFERING | win32file.FILE_FLAG_SEQUENTIAL_SCAN,
            None
        )
        
        try:
            # Prepare for reading
            buffer = bytearray(buffer_size)
            total_bytes_read = 0
            
            start_time = time.time()
            
            # Read until we've processed the whole file
            while total_bytes_read < file_size_bytes:
                # Read a chunk (properly aligned)
                error, data = win32file.ReadFile(handle, buffer)
                
                if error != 0:
                    raise Exception(f"ReadFile error: {error}")
                
                if not data:
                    # End of file
                    break
                    
                total_bytes_read += len(data)
            
            end_time = time.time()
            
            # Calculate throughput
            duration = end_time - start_time
            throughput = file_size_bytes / (1024 * 1024) / duration
            
            return duration, throughput
            
        finally:
            # Always close the handle
            win32file.CloseHandle(handle)
            
    except Exception as e:
        # Log the error and fall back to standard reading
        print(f"Direct I/O failed (install PyWin32 or run as admin): {e}")
        return standard_reading()


def read_benchmark(drive_path: str, num_files: int = 10, file_size_mb: int = 10,
                test_latency: bool = True, test_throughput: bool = True,
                latency_file_count: int = 50, throughput_file_size_mb: int = 50) -> Dict:
    """
    Perform read benchmark test.
    
    Args:
        drive_path: Path to the drive
        num_files: Number of files to read
        file_size_mb: Size of each file in MB
        test_latency: Whether to run small file latency tests
        test_throughput: Whether to run large file throughput tests
        latency_file_count: Number of small files for latency test
        throughput_file_size_mb: Size of each file for throughput test
        
    Returns:
        Dictionary with benchmark results
    """
    results = {}
    
    # Latency-optimized test (small files, many operations)
    if test_latency:
        print(f"\nPerforming read LATENCY benchmark on {drive_path}...")
        
        # Create a benchmark directory with unique name
        timestamp = int(time.time())
        benchmark_dir = os.path.join(drive_path, f"benchmark_test_lat_{timestamp}")
        if os.path.exists(benchmark_dir):
            shutil.rmtree(benchmark_dir)
        os.makedirs(benchmark_dir)
        
        latency_file_size_kb = 4  # Small 4KB files for latency testing
        
        # First, write all files for latency test
        print(f"Preparing {latency_file_count} small files ({latency_file_size_kb}KB each)...")
        file_paths = []
        
        # Progress bar for file creation
        for i in range(latency_file_count):
            # Update progress bar
            progress = (i + 1) / latency_file_count * 100
            bar_length = 30
            filled_length = int(bar_length * (i + 1) // latency_file_count)
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            print(f"\rCreating files: [{bar}] {progress:.1f}%", end='')
            
            # Generate unique data for each file
            data = os.urandom(latency_file_size_kb * 1024)
            file_path = os.path.join(benchmark_dir, f"test_lat_{i}_{timestamp}.bin")
            with open(file_path, 'wb') as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            file_paths.append(file_path)
        
        print("\nFiles created. Starting read test...")
        
        # Wait a moment to ensure writes are completed and files are not in cache
        time.sleep(1)
        
        # Force files out of cache
        clear_cache()
        
        # Now read files for latency benchmark
        print(f"Reading {latency_file_count} small files for latency test...")
        latencies = []
        
        # Only clear cache once before the batch for quick tests
        if latency_file_count <= 20:
            clear_cache()
            
        for i, file_path in enumerate(file_paths):
            # Update progress bar
            progress = (i + 1) / latency_file_count * 100
            bar_length = 30
            filled_length = int(bar_length * (i + 1) // latency_file_count)
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            print(f"\rProgress: [{bar}] {progress:.1f}%", end='')
            
            # Clear cache only periodically for larger tests
            if latency_file_count > 20 and i % 5 == 0:
                clear_cache()
            
            # Time the read operation
            start_time = time.time()
            with open(file_path, 'rb') as f:
                read_data = f.read()
            end_time = time.time()
            
            duration = end_time - start_time
            latencies.append(duration)
        
        print("\nLatency test completed.")
        
        # Clean up
        shutil.rmtree(benchmark_dir)
        
        results.update({
            "read_latency_avg": statistics.mean(latencies),
            "read_latency_min": min(latencies),
            "read_latency_max": max(latencies),
            "read_latency_median": statistics.median(latencies),
            "read_latency_file_size_kb": latency_file_size_kb,
            "read_latency_file_count": latency_file_count
        })
    
    # Throughput-optimized test (large files, fewer operations)
    if test_throughput:
        print(f"\nPerforming read THROUGHPUT benchmark on {drive_path}...")
        
        # Create a benchmark directory with unique name
        timestamp = int(time.time())
        benchmark_dir = os.path.join(drive_path, f"benchmark_test_thr_{timestamp}")
        if os.path.exists(benchmark_dir):
            shutil.rmtree(benchmark_dir)
        os.makedirs(benchmark_dir)
        
        throughput_file_count = min(3, num_files)  # Fewer operations for throughput
        
        # Use slightly larger files for accurate throughput testing
        actual_file_size_mb = throughput_file_size_mb * 2
        
        # First, write all files for throughput test
        file_paths = []
        file_sizes = []  # Track exact file sizes
        
        for i in range(throughput_file_count):
            print(f"Preparing large file {i+1}/{throughput_file_count} ({actual_file_size_mb}MB)...")
            
            # Generate unique data for each file - use random patterns to defeat compression
            # and make the test more realistic
            chunk_size = 1024 * 1024  # 1MB chunks for better memory management
            file_path = os.path.join(benchmark_dir, f"test_thr_{i}_{timestamp}.bin")
            
            with open(file_path, 'wb') as f:
                for j in range(actual_file_size_mb):
                    # Show progress for large file creation
                    progress = (j + 1) / actual_file_size_mb * 100
                    bar_length = 30
                    filled_length = int(bar_length * (j + 1) // actual_file_size_mb)
                    bar = '█' * filled_length + '░' * (bar_length - filled_length)
                    print(f"\rCreating file: [{bar}] {progress:.1f}%", end='')
                    
                    # Use truly random data for each MB to defeat compression
                    # and make the test more realistic
                    f.write(os.urandom(chunk_size))
                    
                f.flush()
                os.fsync(f.fileno())
            
            file_paths.append(file_path)
            file_sizes.append(actual_file_size_mb * 1024 * 1024)  # Store size in bytes
            print()  # Newline after progress bar
        
        # Wait a moment to ensure writes are completed
        time.sleep(2)
        
        # Force files out of cache
        clear_cache()
        time.sleep(1)  # Additional wait to ensure cache is cleared
        
        # Now read files for throughput benchmark using direct I/O
        throughputs = []
        
        for i, (file_path, file_size) in enumerate(zip(file_paths, file_sizes)):
            print(f"Reading large file {i+1}/{throughput_file_count} for throughput test...")
            print("Using direct I/O (NO_BUFFERING) to bypass cache...")
            
            # Clear cache before each read
            clear_cache()
            
            # Read with direct I/O
            duration, throughput = read_with_no_buffering(file_path, file_size)
            
            throughputs.append(throughput)
            
            print(f"File {i+1}: Read throughput: {throughput:.2f} MB/s ({duration:.2f}s)")
        
        # Clean up
        shutil.rmtree(benchmark_dir)
        
        results.update({
            "read_throughput_avg": statistics.mean(throughputs),
            "read_throughput_min": min(throughputs),
            "read_throughput_max": max(throughputs),
            "read_throughput_file_size_mb": actual_file_size_mb,
            "read_throughput_file_count": throughput_file_count
        })
    
    return results

def random_seek_benchmark(drive_path: str, num_seeks: int = 100, file_size_mb: int = 100) -> Dict:
    """
    Perform random seek benchmark.
    
    Args:
        drive_path: Path to the drive
        num_seeks: Number of random seeks to perform
        file_size_mb: Size of the test file in MB
        
    Returns:
        Dictionary with benchmark results
    """
    print(f"\nPerforming random seek benchmark on {drive_path}...")
    
    # Use a smaller file size if num_seeks is small (for quick test)
    if num_seeks <= 30:
        file_size_mb = min(file_size_mb, 30)  # Smaller file for quick test
    
    # Create a benchmark directory with unique name
    timestamp = int(time.time())
    benchmark_dir = os.path.join(drive_path, f"benchmark_test_{timestamp}")
    if os.path.exists(benchmark_dir):
        shutil.rmtree(benchmark_dir)
    os.makedirs(benchmark_dir)
    
    # Create a large file for random seeking with random data
    file_path = os.path.join(benchmark_dir, f"large_file_{timestamp}.bin")
    file_size_bytes = file_size_mb * 1024 * 1024
    
    print(f"Creating test file ({file_size_mb}MB)...")
    # Write the file in chunks with unique random data to prevent compression
    chunk_size = 1024 * 1024  # 1 MB
    with open(file_path, 'wb') as f:
        for i in range(file_size_mb):
            # Show progress for large file creation
            progress = (i + 1) / file_size_mb * 100
            bar_length = 30
            filled_length = int(bar_length * (i + 1) // file_size_mb)
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            print(f"\rCreating test file: [{bar}] {progress:.1f}%", end='')
            
            f.write(os.urandom(chunk_size))
            f.flush()
    
    print("\nFile created. Starting seek test...")
    # Wait a moment to ensure writes are completed
    time.sleep(1)
    
    latencies = []
    
    # Generate random positions for seeking
    max_pos = file_size_bytes - 4096  # Leave room for reading a small block
    positions = [random.randint(0, max_pos) for _ in range(num_seeks)]
    
    print(f"Starting random seek test ({num_seeks} seeks)...")
    with open(file_path, 'rb') as f:
        # Only clear cache once if number of seeks is small (quick test)
        if num_seeks <= 30:
            clear_cache()
        
        for i, pos in enumerate(positions):
            # Update progress bar
            progress = (i + 1) / num_seeks * 100
            bar_length = 30
            filled_length = int(bar_length * (i + 1) // num_seeks)
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            print(f"\rProgress: [{bar}] {progress:.1f}% ({i+1}/{num_seeks})", end='')
            
            # Clear cache only periodically for larger tests to save time
            if num_seeks > 30 and i % 5 == 0:
                clear_cache()
            
            # Time the seek and read operation
            start_time = time.time()
            f.seek(pos)
            # Read 4KB block to simulate real access
            _ = f.read(4096)  
            end_time = time.time()
            
            duration = end_time - start_time
            latencies.append(duration)
    
    print("\nRandom seek test completed.")
    
    # Clean up
    shutil.rmtree(benchmark_dir)
    
    return {
        "seek_latency_avg": statistics.mean(latencies),
        "seek_latency_min": min(latencies),
        "seek_latency_max": max(latencies),
        "seek_latency_median": statistics.median(latencies),
        "num_seeks": num_seeks,
        "file_size_mb": file_size_mb
    }

def display_results(drive_info: Dict, write_results: Dict, read_results: Dict, seek_results: Dict):
    """Display benchmark results to the console."""
    print("\n" + "="*60)
    print("USB FLASH DRIVE BENCHMARK RESULTS")
    print("="*60)
    
    print(f"\nDrive Information:")
    print(f"  Drive Letter: {drive_info['DriveLetter']}")
    volume_name = drive_info.get('VolumeName', 'No Label')
    print(f"  Volume Name: {volume_name}")
    print(f"  Capacity: {drive_info['SizeGB']} GB")
    
    model = drive_info.get('Model', 'Unknown Model')
    print(f"  Model: {model}")
    
    vendor = drive_info.get('Vendor', 'Unknown Vendor')
    print(f"  Vendor: {vendor}")
    
    if 'SerialNumber' in drive_info and drive_info['SerialNumber']:
        print(f"  Serial Number: {drive_info['SerialNumber']}")
    
    print("\nLATENCY PERFORMANCE (lower is better):")
    print("-" * 40)
    # Seek latency
    print(f"  Random Seek Latency: {seek_results['seek_latency_avg']*1000:.2f} ms (avg)")
    print(f"  Random Seek Latency: {seek_results['seek_latency_min']*1000:.2f} ms (min)")
    print(f"  Random Seek Latency: {seek_results['seek_latency_median']*1000:.2f} ms (median)")
    print(f"  Random Seek Latency: {seek_results['seek_latency_max']*1000:.2f} ms (max)")
    
    # Write latency
    if 'write_latency_avg' in write_results:
        print(f"  Write Latency: {write_results['write_latency_avg']*1000:.2f} ms (avg)")
        print(f"  Write Latency: {write_results['write_latency_min']*1000:.2f} ms (min)")
        print(f"  Write Latency: {write_results['write_latency_median']*1000:.2f} ms (median)")
        print(f"  Write Latency: {write_results['write_latency_max']*1000:.2f} ms (max)")
    
    # Read latency
    if 'read_latency_avg' in read_results:
        print(f"  Read Latency: {read_results['read_latency_avg']*1000:.2f} ms (avg)")
        print(f"  Read Latency: {read_results['read_latency_min']*1000:.2f} ms (min)")
        print(f"  Read Latency: {read_results['read_latency_median']*1000:.2f} ms (median)")
        print(f"  Read Latency: {read_results['read_latency_max']*1000:.2f} ms (max)")
    
    print("\nTHROUGHPUT PERFORMANCE (higher is better):")
    print("-" * 40)
    # Write throughput
    if 'write_throughput_avg' in write_results:
        print(f"  Write Throughput: {write_results['write_throughput_avg']:.2f} MB/s (avg)")
        print(f"  Write Throughput: {write_results['write_throughput_min']:.2f} MB/s (min)")
        print(f"  Write Throughput: {write_results['write_throughput_max']:.2f} MB/s (max)")
    
    # Read throughput
    if 'read_throughput_avg' in read_results:
        print(f"  Read Throughput: {read_results['read_throughput_avg']:.2f} MB/s (avg)")
        print(f"  Read Throughput: {read_results['read_throughput_min']:.2f} MB/s (min)")
        print(f"  Read Throughput: {read_results['read_throughput_max']:.2f} MB/s (max)")
    
    print("\nTest Parameters:")
    print("-" * 40)
    # Latency tests
    if 'write_latency_file_count' in write_results:
        print(f"  Write Latency Test: {write_results['write_latency_file_count']} files, "
              f"{write_results['write_latency_file_size_kb']} KB each")
    if 'read_latency_file_count' in read_results:
        print(f"  Read Latency Test: {read_results['read_latency_file_count']} files, "
              f"{read_results['read_latency_file_size_kb']} KB each")
    
    # Throughput tests
    if 'write_throughput_file_count' in write_results:
        print(f"  Write Throughput Test: {write_results['write_throughput_file_count']} files, "
              f"{write_results['write_throughput_file_size_mb']} MB each")
    if 'read_throughput_file_count' in read_results:
        print(f"  Read Throughput Test: {read_results['read_throughput_file_count']} files, "
              f"{read_results['read_throughput_file_size_mb']} MB each")
    
    print(f"  Seek Test: {seek_results['num_seeks']} random seeks in a {seek_results['file_size_mb']} MB file")
    print("="*60)

def main():
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
        throughput_test = True  # Changed to True to include throughput test
        latency_file_count = 15      # Reduced from 50
        throughput_file_size_mb = 20 # Reduced from 50
        seek_count = 20              # Reduced from 50
    elif test_choice == "2":  # Standard
        print("\nRunning standard test (approx. 2-3 minutes)...")
        latency_test = True
        throughput_test = True
        latency_file_count = 25      # Reduced from 50
        throughput_file_size_mb = 25 # Reduced from 50
        seek_count = 50              # Reduced from 100
    elif test_choice == "3":  # Thorough
        print("\nRunning thorough test (approx. 5-8 minutes)...")
        latency_test = True
        throughput_test = True
        latency_file_count = 50       # Standard amount
        throughput_file_size_mb = 50  # Standard size
        seek_count = 100              # Standard amount
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
        except:
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
    except Exception as e:
        print(f"Error during benchmark: {e}")
        print("Benchmark failed. Please check if the drive is still connected and has sufficient space.")

if __name__ == "__main__":
    main()