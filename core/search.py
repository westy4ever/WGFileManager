import os
import subprocess
import threading
from fnmatch import fnmatch
from ..exceptions import FileOperationError
from ..utils.validators import validate_path
from ..utils.formatters import format_size

class SearchEngine:
    def __init__(self, cache=None):
        self.cache = cache
        # FIXED: Use threading.Event() correctly
        self._stop_search = threading.Event()
        self._search_lock = threading.Lock()
    
    def search_files(self, directory, pattern, recursive=True, max_results=100):
        """Search for files matching pattern"""
        try:
            validate_path(directory)
            
            if not os.path.isdir(directory):
                raise FileOperationError(f"Not a directory: {directory}")
            
            self._stop_search.clear()
            results = []
            
            if recursive:
                for root, dirs, files in os.walk(directory):
                    if self._stop_search.is_set():
                        break
                    
                    # Search in files
                    for name in files:
                        if self._stop_search.is_set():
                            break
                        
                        if fnmatch(name.lower(), pattern.lower()):
                            full_path = os.path.join(root, name)
                            results.append({
                                'path': full_path,
                                'name': name,
                                'is_dir': False,
                                'size': os.path.getsize(full_path) if os.path.exists(full_path) else 0
                            })
                        
                        if len(results) >= max_results:
                            self._stop_search.set()
                            break
                    
                    # Search in directory names
                    for name in dirs:
                        if self._stop_search.is_set():
                            break
                        
                        if fnmatch(name.lower(), pattern.lower()):
                            full_path = os.path.join(root, name)
                            results.append({
                                'path': full_path,
                                'name': name,
                                'is_dir': True,
                                'size': 0
                            })
                        
                        if len(results) >= max_results:
                            self._stop_search.set()
                            break
            else:
                # Non-recursive search
                try:
                    entries = os.listdir(directory)
                    for name in entries:
                        if self._stop_search.is_set():
                            break
                        
                        if fnmatch(name.lower(), pattern.lower()):
                            full_path = os.path.join(directory, name)
                            is_dir = os.path.isdir(full_path)
                            results.append({
                                'path': full_path,
                                'name': name,
                                'is_dir': is_dir,
                                'size': 0 if is_dir else os.path.getsize(full_path)
                            })
                        
                        if len(results) >= max_results:
                            self._stop_search.set()
                            break
                except Exception:
                    pass
            
            return results
            
        except Exception as e:
            raise FileOperationError(f"File search failed: {e}")
    
    def search_content(self, directory, text, file_pattern="*", recursive=True, max_results=50):
        """Search for text inside files using grep"""
        try:
            validate_path(directory)
            
            if not os.path.isdir(directory):
                raise FileOperationError(f"Not a directory: {directory}")
            
            self._stop_search.clear()
            
            # Check if grep is available
            try:
                subprocess.run(["which", "grep"], capture_output=True, check=True)
            except:
                raise FileOperationError("grep command not found")
            
            # Build grep command
            cmd = ["grep", "-l", "-i", text]
            
            if recursive:
                cmd.extend(["-r", directory])
            else:
                try:
                    files = [f for f in os.listdir(directory) 
                            if os.path.isfile(os.path.join(directory, f))]
                    if not files:
                        return []
                    cmd.extend([os.path.join(directory, f) for f in files])
                except:
                    return []
            
            if file_pattern and file_pattern != "*":
                cmd.extend(["--include", file_pattern])
            
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    files = result.stdout.strip().split('\n')
                    files = [f for f in files if f]
                    
                    results = []
                    for file_path in files[:max_results]:
                        if self._stop_search.is_set():
                            break
                        
                        if os.path.exists(file_path):
                            results.append({
                                'path': file_path,
                                'name': os.path.basename(file_path),
                                'is_dir': False,
                                'size': os.path.getsize(file_path)
                            })
                    
                    return results
                elif result.returncode == 1:
                    return []
                else:
                    raise FileOperationError(f"grep error: {result.stderr[:100]}")
                    
            except subprocess.TimeoutExpired:
                raise FileOperationError("Search timed out")
            except Exception as e:
                raise FileOperationError(f"Content search failed: {e}")
            
        except Exception as e:
            if isinstance(e, FileOperationError):
                raise
            raise FileOperationError(f"Content search failed: {e}")
    
    def find_large_files(self, directory, min_size_mb=100, max_results=50):
        """Find files larger than specified size"""
        try:
            validate_path(directory)
            
            if not os.path.isdir(directory):
                raise FileOperationError(f"Not a directory: {directory}")
            
            min_size = min_size_mb * 1024 * 1024
            results = []
            
            for root, dirs, files in os.walk(directory):
                if self._stop_search.is_set():
                    break
                
                for name in files:
                    if self._stop_search.is_set():
                        break
                    
                    full_path = os.path.join(root, name)
                    try:
                        size = os.path.getsize(full_path)
                        if size >= min_size:
                            results.append({
                                'path': full_path,
                                'name': name,
                                'size': size,
                                'size_formatted': format_size(size),
                                'directory': root
                            })
                        
                        if len(results) >= max_results:
                            self._stop_search.set()
                            break
                    except:
                        continue
            
            results.sort(key=lambda x: x['size'], reverse=True)
            return results
            
        except Exception as e:
            raise FileOperationError(f"Find large files failed: {e}")
    
    def find_duplicates(self, directory, max_results=50):
        """Find duplicate files by size and name"""
        try:
            validate_path(directory)
            
            if not os.path.isdir(directory):
                raise FileOperationError(f"Not a directory: {directory}")
            
            file_map = {}
            duplicates = []
            
            for root, dirs, files in os.walk(directory):
                if self._stop_search.is_set():
                    break
                
                for name in files:
                    if self._stop_search.is_set():
                        break
                    
                    full_path = os.path.join(root, name)
                    try:
                        size = os.path.getsize(full_path)
                        key = f"{name}_{size}"
                        
                        if key in file_map:
                            file_map[key].append(full_path)
                        else:
                            file_map[key] = [full_path]
                    except:
                        continue
            
            for key, paths in file_map.items():
                if len(paths) > 1:
                    duplicates.append({
                        'name': key.split('_')[0],
                        'size': int(key.split('_')[1]),
                        'paths': paths,
                        'count': len(paths)
                    })
                
                if len(duplicates) >= max_results:
                    break
            
            return duplicates
            
        except Exception as e:
            raise FileOperationError(f"Find duplicates failed: {e}")
    
    def stop_search(self):
        """Stop current search operation"""
        with self._search_lock:
            self._stop_search.set()
    
    def is_searching(self):
        """Check if search is in progress"""
        with self._search_lock:
            return not self._stop_search.is_set()
