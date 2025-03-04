"""
Core benchmark functions for USB flash drive performance testing.
"""
import os
import random
import time
import shutil
import statistics
from typing import Dict

from utils import clear_cache, read_with_no_buffering

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