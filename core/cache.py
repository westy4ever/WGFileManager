import json
import os
import threading
from collections import OrderedDict
from ..constants import CACHE_FILE, MAX_CACHE_SIZE

class FileCache:
    def __init__(self, max_size=MAX_CACHE_SIZE, cache_file=None):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.cache_file = cache_file or CACHE_FILE
        self.hits = 0
        self.misses = 0
        self.lock = threading.RLock()
        self.load_cache()
    
    def load_cache(self):
        """Load cache from file"""
        if self.cache_file and os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    for key, value in data.items():
                        self.cache[key] = value
                return True
            except Exception:
                pass
        return False
    
    def save_cache(self):
        """Save cache to file"""
        if self.cache_file:
            try:
                with open(self.cache_file, 'w') as f:
                    json.dump(dict(self.cache), f)
                return True
            except Exception:
                pass
        return False
    
    def get(self, key, default=None):
        """Get value from cache"""
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                self.hits += 1
                return self.cache[key]
            self.misses += 1
            return default
    
    def set(self, key, value):
        """Set value in cache"""
        with self.lock:
            self.cache[key] = value
            self.cache.move_to_end(key)
            # Evict oldest items until within budget (load may overfill)
            while len(self.cache) > self.max_size:
                self.cache.popitem(last=False)
            return True
    
    def delete(self, key):
        """Delete key from cache"""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                return True
            return False
    
    def clear(self):
        """Clear cache"""
        with self.lock:
            self.cache.clear()
            self.hits = 0
            self.misses = 0
            return True
    
    def get_stats(self):
        """Get cache statistics"""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return {
            'size': len(self.cache),
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': f"{hit_rate:.1f}%"
        }
    
    def __contains__(self, key):
        with self.lock:
            return key in self.cache
    
    def __len__(self):
        return len(self.cache)