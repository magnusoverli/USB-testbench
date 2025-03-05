"""
Utility functions for USB flash drive benchmark tool.
"""
import os
import random
import time
import subprocess
import tempfile
import json
import ctypes
import gc
import hashlib
from typing import List, Dict, Tuple

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
    """Get a list of connected USB flash drives including SCSI-reported USB devices."""
    # Enhanced PowerShell command to detect all types of USB storage devices
    ps_command = """
    Get-WmiObject Win32_DiskDrive | 
    Where-Object { 
        # Traditional USB removable drives
        ($_.InterfaceType -eq "USB" -and $_.MediaType -like "*removable*") -or
        
        # External USB drives that report as SCSI
        (
            # Model name contains USB
            ($_.Model -like "*USB*" -or $_.Caption -like "*USB*") -or 
            
            # Device ID contains USB
            ($_.PNPDeviceID -like "*USB*") -or
            
            # Handle external drives even without USB in name
            ($_.MediaType -eq "External hard disk media")
        )
    } | 
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
                    PNPDeviceID = $disk.PNPDeviceID
                    FirmwareRevision = $disk.FirmwareRevision
                    Signature = $disk.Signature
                    Index = $disk.Index
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
            result = [result]
            
        # Generate a unique identifier for each device
        for drive in result:
            drive['device_id'] = generate_device_id(drive)
            
        return result
    except json.JSONDecodeError:
        print(f"Error parsing JSON output: {process.stdout}")
        return []

def generate_device_id(drive: Dict) -> str:
    """
    Generate a unique device identifier from drive information.
    Uses a combination of serial number, hardware signature, and other identifiers.
    """
    # Components to use for the unique ID
    components = []
    
    # Serial number (most important)
    serial = drive.get('SerialNumber', '')
    if serial:
        components.append(f"SN:{serial}")
    
    # Hardware signature
    signature = drive.get('Signature', '')
    if signature:
        components.append(f"SIG:{signature}")
    
    # PNP Device ID (contains hardware identifiers)
    pnp_id = drive.get('PNPDeviceID', '')
    if pnp_id:
        components.append(f"PNP:{pnp_id}")
    
    # Add model and vendor if available
    model = drive.get('Model', '')
    if model:
        components.append(f"MDL:{model}")
    
    vendor = drive.get('Vendor', '')
    if vendor:
        components.append(f"VDR:{vendor}")
    
    # If we still don't have enough information, add size
    if len(components) < 2:
        size = drive.get('SizeGB', 0)
        components.append(f"SZ:{size}")
    
    # Create a hash for a shorter ID
    if components:
        # Join components and create SHA-256 hash
        component_str = "|".join(components)
        hash_obj = hashlib.sha256(component_str.encode())
        
        # Use first 16 chars of hash for reasonable length
        device_id = hash_obj.hexdigest()[:16]
        
        # Also store the original components for debugging/verification
        drive['id_components'] = component_str
        
        return device_id
    else:
        # Fallback if no identifiable information is available
        # Use a timestamp + random value (not ideal but prevents errors)
        return f"UNKNOWN_{int(time.time())}_{random.randint(1000, 9999)}"

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
        device_id = drive.get('device_id', 'Unknown ID')
        
        print(f"{i+1}. {drive['DriveLetter']} - {volume_name} ({drive['SizeGB']} GB)")
        print(f"   Model: {model} | Vendor: {vendor}")
        print(f"   Device ID: {device_id}")
    
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
    gc.collect()
    
    # Shorter sleep time
    time.sleep(0.25)  # Reduced from 1s to 0.25s

def read_with_no_buffering(file_path: str, file_size_bytes: int) -> Tuple[float, float]:
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
    
    print(f"  Device ID: {drive_info['device_id']}")
    
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