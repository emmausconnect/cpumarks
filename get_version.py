"""Get version information for cpumarks project"""
import os
import sys
import json
import time
from pathlib import Path

# Import version from __version__.py
try:
    from __version__ import __version__
except ImportError:
    __version__ = "unknown"


def get_version_info(marksdata_dir: str = None) -> dict:
    """
    Returns version information including project version and current CSV file info
    
    Args:
        marksdata_dir: Path to marksdata directory (optional, auto-detected if not provided)
    
    Returns:
        Dictionary with version information
    """
    if marksdata_dir is None:
        marksdata_dir = os.path.join(os.path.dirname(__file__), 'marksdata')
    
    result = {
        "project_version": __version__,
        "csv_symlink": None,  # ← NOUVEAU
        "csv_target": None,   # ← NOUVEAU
        "csv_file": None,
        "csv_basename": None,
        "csv_modified_time": None,
        "csv_modified_iso": None,
        "total_cpus": None,
    }
    
    # Find the current CSV file (follow symlink)
    csv_link = os.path.join(marksdata_dir, 'cpumarks.csv')
    result["csv_symlink"] = csv_link  # ← NOUVEAU
    
    if os.path.islink(csv_link):
        # Get the target of the symlink
        csv_target = os.readlink(csv_link)
        result["csv_target"] = csv_target  # ← NOUVEAU (nom relatif)
        csv_file = os.path.join(marksdata_dir, csv_target)
        result["csv_basename"] = csv_target
    elif os.path.isfile(csv_link):
        # Direct file (not a symlink)
        csv_file = csv_link
        result["csv_basename"] = "cpumarks.csv"
        result["csv_target"] = None  # ← Pas un symlink
    else:
        return result  # No CSV file found
    
    result["csv_file"] = csv_file
    
    # Get modification time
    if os.path.isfile(csv_file):
        mtime = os.path.getmtime(csv_file)
        result["csv_modified_time"] = int(mtime)
        result["csv_modified_iso"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
        
        # Count lines (approximate CPU count)
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                line_count = sum(1 for _ in f) - 1  # -1 for header
            result["total_cpus"] = line_count
        except Exception:
            pass
    
    return result

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Get cpumarks project version information')
    parser.add_argument('--marksdata-dir', type=str, help='Path to marksdata directory')
    parser.add_argument('--pretty', action='store_true', help='Pretty print JSON output')
    
    args = parser.parse_args()
    
    info = get_version_info(args.marksdata_dir)
    
    if args.pretty:
        print(json.dumps(info, indent=2))
    else:
        print(json.dumps(info))
    
    sys.exit(0)