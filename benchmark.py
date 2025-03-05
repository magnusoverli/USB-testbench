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

def write_with_no_buffering(file_path: str, data: bytes) -> float:
    """
    Write data to file using direct I/O if available.
    Pads data to a multiple of 4096 bytes if needed.
    Returns the duration of the write operation.
    """
    block_size = 4096
    # Pad data so its length is a multiple of block_size.
    if len(data) % block_size != 0:
        pad_length = block_size - (len(data) % block_size)
        data += b'\0' * pad_length

    flags = os.O_WRONLY | os.O_CREAT
    if hasattr(os, 'O_DIRECT'):
        flags |= os.O_DIRECT

    start_time = time.time()
    fd = os.open(file_path, flags, 0o666)
    bytes_written = 0
    try:
        # Write in a loop until complete.
        while bytes_written < len(data):
            n = os.write(fd, data[bytes_written:])
            if n == 0:
                break
            bytes_written += n
        os.fsync(fd)
    finally:
        os.close(fd)
    return time.time() - start_time

def write_benchmark(drive_path: str, num_files: int = 10, file_size_mb: int = 10, 
                    test_latency: bool = True, test_throughput: bool = True,
                    latency_file_count: int = 50, throughput_file_size_mb: int = 50,
                    extended_throughput: bool = False) -> Dict:
    """
    Perform write benchmark tests.
    
    - Latency: Writes many small (4KB) files.
    - Throughput: Writes fewer large files using direct I/O if available.
    
    The extended_throughput flag uses larger files (default 1GB) for sustained performance.
    """
    results = {}
    
    # Use larger files for extended throughput tests.
    if extended_throughput and throughput_file_size_mb < 1024:
        throughput_file_size_mb = 1024  # 1GB files
    
    # --- Latency Test ---
    if test_latency:
        print(f"\nPerforming write LATENCY benchmark on {drive_path}...")
        timestamp = int(time.time())
        benchmark_dir = os.path.join(drive_path, f"benchmark_test_lat_{timestamp}")
        if os.path.exists(benchmark_dir):
            shutil.rmtree(benchmark_dir)
        os.makedirs(benchmark_dir)
        
        latency_file_size_kb = 4  # 4KB files
        latencies = []
        print(f"Writing {latency_file_count} small files ({latency_file_size_kb}KB each)...")
        
        if latency_file_count <= 20:
            clear_cache()
            
        for i in range(latency_file_count):
            progress = (i + 1) / latency_file_count * 100
            bar_length = 30
            filled_length = int(bar_length * (i + 1) // latency_file_count)
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            print(f"\rProgress: [{bar}] {progress:.1f}%", end='')
            
            data = os.urandom(latency_file_size_kb * 1024)
            file_path = os.path.join(benchmark_dir, f"test_lat_{i}_{timestamp}.bin")
            
            if latency_file_count > 20 and i % 5 == 0:
                clear_cache()
            
            start_time = time.time()
            with open(file_path, 'wb') as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            latencies.append(time.time() - start_time)
        
        print("\nLatency test completed.")
        shutil.rmtree(benchmark_dir)
        results.update({
            "write_latency_avg": statistics.mean(latencies),
            "write_latency_min": min(latencies),
            "write_latency_max": max(latencies),
            "write_latency_median": statistics.median(latencies),
            "write_latency_file_size_kb": latency_file_size_kb,
            "write_latency_file_count": latency_file_count
        })
    
    # --- Throughput Test ---
    if test_throughput:
        print(f"\nPerforming write THROUGHPUT benchmark on {drive_path}...")
        timestamp = int(time.time())
        benchmark_dir = os.path.join(drive_path, f"benchmark_test_thr_{timestamp}")
        if os.path.exists(benchmark_dir):
            shutil.rmtree(benchmark_dir)
        os.makedirs(benchmark_dir)
        
        throughput_file_count = min(3, num_files)
        throughputs = []
        
        for i in range(throughput_file_count):
            print(f"\nWriting large file {i+1}/{throughput_file_count} ({throughput_file_size_mb}MB)...")
            data = os.urandom(throughput_file_size_mb * 1024 * 1024)
            file_path = os.path.join(benchmark_dir, f"test_thr_{i}_{timestamp}.bin")
            clear_cache()
            try:
                duration = write_with_no_buffering(file_path, data)
            except Exception as e:
                print(f"Direct I/O write failed: {e}. Falling back to standard write.")
                start_time = time.time()
                with open(file_path, 'wb') as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                duration = time.time() - start_time
            
            throughput = throughput_file_size_mb / duration
            throughputs.append(throughput)
            print(f"File {i+1}: Write throughput: {throughput:.2f} MB/s ({duration:.2f}s)")
        
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
                   latency_file_count: int = 50, throughput_file_size_mb: int = 50,
                   extended_throughput: bool = False) -> Dict:
    """
    Perform read benchmark tests.
    
    - Latency: Reads many small (4KB) files.
    - Throughput: Reads large files (using direct I/O via read_with_no_buffering).
    
    The extended_throughput flag uses larger files (default 1GB read test files, doubled in size).
    """
    results = {}
    
    if extended_throughput and throughput_file_size_mb < 1024:
        throughput_file_size_mb = 1024  # 1GB files
    
    # --- Latency Test ---
    if test_latency:
        print(f"\nPerforming read LATENCY benchmark on {drive_path}...")
        timestamp = int(time.time())
        benchmark_dir = os.path.join(drive_path, f"benchmark_test_lat_{timestamp}")
        if os.path.exists(benchmark_dir):
            shutil.rmtree(benchmark_dir)
        os.makedirs(benchmark_dir)
        
        latency_file_size_kb = 4  # 4KB files
        print(f"Preparing {latency_file_count} small files ({latency_file_size_kb}KB each)...")
        file_paths = []
        
        for i in range(latency_file_count):
            progress = (i + 1) / latency_file_count * 100
            bar_length = 30
            filled_length = int(bar_length * (i + 1) // latency_file_count)
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            print(f"\rCreating files: [{bar}] {progress:.1f}%", end='')
            data = os.urandom(latency_file_size_kb * 1024)
            file_path = os.path.join(benchmark_dir, f"test_lat_{i}_{timestamp}.bin")
            with open(file_path, 'wb') as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            file_paths.append(file_path)
        
        print("\nFiles created. Starting read test...")
        time.sleep(1)
        clear_cache()
        latencies = []
        
        if latency_file_count <= 20:
            clear_cache()
            
        for i, file_path in enumerate(file_paths):
            progress = (i + 1) / latency_file_count * 100
            bar_length = 30
            filled_length = int(bar_length * (i + 1) // latency_file_count)
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            print(f"\rProgress: [{bar}] {progress:.1f}%", end='')
            if latency_file_count > 20 and i % 5 == 0:
                clear_cache()
            start_time = time.time()
            with open(file_path, 'rb') as f:
                _ = f.read()
            latencies.append(time.time() - start_time)
        
        print("\nLatency test completed.")
        shutil.rmtree(benchmark_dir)
        results.update({
            "read_latency_avg": statistics.mean(latencies),
            "read_latency_min": min(latencies),
            "read_latency_max": max(latencies),
            "read_latency_median": statistics.median(latencies),
            "read_latency_file_size_kb": latency_file_size_kb,
            "read_latency_file_count": latency_file_count
        })
    
    # --- Throughput Test ---
    if test_throughput:
        print(f"\nPerforming read THROUGHPUT benchmark on {drive_path}...")
        timestamp = int(time.time())
        benchmark_dir = os.path.join(drive_path, f"benchmark_test_thr_{timestamp}")
        if os.path.exists(benchmark_dir):
            shutil.rmtree(benchmark_dir)
        os.makedirs(benchmark_dir)
        
        throughput_file_count = min(3, num_files)
        # Double the file size for the read test to capture sustained performance.
        actual_file_size_mb = throughput_file_size_mb * 2
        
        file_paths = []
        file_sizes = []
        
        for i in range(throughput_file_count):
            print(f"Preparing large file {i+1}/{throughput_file_count} ({actual_file_size_mb}MB)...")
            chunk_size = 1024 * 1024  # 1MB
            file_path = os.path.join(benchmark_dir, f"test_thr_{i}_{timestamp}.bin")
            with open(file_path, 'wb') as f:
                for j in range(actual_file_size_mb):
                    progress = (j + 1) / actual_file_size_mb * 100
                    bar_length = 30
                    filled_length = int(bar_length * (j + 1) // actual_file_size_mb)
                    bar = '█' * filled_length + '░' * (bar_length - filled_length)
                    print(f"\rCreating file: [{bar}] {progress:.1f}%", end='')
                    f.write(os.urandom(chunk_size))
                f.flush()
                os.fsync(f.fileno())
            file_paths.append(file_path)
            file_sizes.append(actual_file_size_mb * 1024 * 1024)
            print()
        
        time.sleep(2)
        clear_cache()
        time.sleep(1)
        
        throughputs = []
        
        for i, (file_path, file_size) in enumerate(zip(file_paths, file_sizes)):
            print(f"Reading large file {i+1}/{throughput_file_count} for throughput test...")
            print("Using direct I/O (NO_BUFFERING) to bypass cache...")
            clear_cache()
            duration, throughput = read_with_no_buffering(file_path, file_size)
            throughputs.append(throughput)
            print(f"File {i+1}: Read throughput: {throughput:.2f} MB/s ({duration:.2f}s)")
        
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
    
    Uses direct I/O if available to bypass cache.
    Random seek positions are aligned to 4096 bytes.
    """
    print(f"\nPerforming random seek benchmark on {drive_path}...")
    
    if num_seeks <= 30:
        file_size_mb = min(file_size_mb, 30)
    
    timestamp = int(time.time())
    benchmark_dir = os.path.join(drive_path, f"benchmark_test_{timestamp}")
    if os.path.exists(benchmark_dir):
        shutil.rmtree(benchmark_dir)
    os.makedirs(benchmark_dir)
    
    file_path = os.path.join(benchmark_dir, f"large_file_{timestamp}.bin")
    file_size_bytes = file_size_mb * 1024 * 1024
    
    print(f"Creating test file ({file_size_mb}MB)...")
    chunk_size = 1024 * 1024  # 1MB
    with open(file_path, 'wb') as f:
        for i in range(file_size_mb):
            progress = (i + 1) / file_size_mb * 100
            bar_length = 30
            filled_length = int(bar_length * (i + 1) // file_size_mb)
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            print(f"\rCreating test file: [{bar}] {progress:.1f}%", end='')
            f.write(os.urandom(chunk_size))
            f.flush()
    print("\nFile created. Starting seek test...")
    time.sleep(1)
    
    latencies = []
    block_size = 4096
    max_pos = file_size_bytes - block_size
    # Align positions to 4096 bytes.
    positions = [random.randint(0, max_pos // block_size) * block_size for _ in range(num_seeks)]
    
    use_direct = hasattr(os, 'O_DIRECT')
    if use_direct:
        fd = os.open(file_path, os.O_RDONLY | os.O_DIRECT)
    else:
        f = open(file_path, 'rb')
    
    print(f"Starting random seek test ({num_seeks} seeks)...")
    for i, pos in enumerate(positions):
        progress = (i + 1) / num_seeks * 100
        bar_length = 30
        filled_length = int(bar_length * (i + 1) // num_seeks)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        print(f"\rProgress: [{bar}] {progress:.1f}% ({i+1}/{num_seeks})", end='')
        
        if not use_direct and num_seeks <= 30:
            clear_cache()
        
        start_time = time.time()
        if use_direct:
            os.lseek(fd, pos, os.SEEK_SET)
            _ = os.read(fd, block_size)
        else:
            f.seek(pos)
            _ = f.read(block_size)
        latencies.append(time.time() - start_time)
    
    print("\nRandom seek test completed.")
    
    if use_direct:
        os.close(fd)
    else:
        f.close()
    shutil.rmtree(benchmark_dir)
    
    return {
        "seek_latency_avg": statistics.mean(latencies),
        "seek_latency_min": min(latencies),
        "seek_latency_max": max(latencies),
        "seek_latency_median": statistics.median(latencies),
        "num_seeks": num_seeks,
        "file_size_mb": file_size_mb
    }
