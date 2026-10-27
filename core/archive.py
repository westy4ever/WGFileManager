import os
import zipfile
import tarfile
import tempfile
from datetime import datetime
from ..exceptions import ArchiveError, FileOperationError
from ..utils.validators import validate_path

class ArchiveManager:
    def __init__(self, file_ops):
        self.file_ops = file_ops
    
    def create_archive(self, files, archive_path, archive_type='zip'):
        """Create archive from multiple files"""
        try:
            validate_path(archive_path)
            
            if not files:
                raise ArchiveError("No files selected for archiving")
            
            archive_path = self._ensure_extension(archive_path, archive_type)
            
            if os.path.exists(archive_path):
                raise ArchiveError(f"Archive already exists: {archive_path}")
            
            # Check if all files exist
            for file_path in files:
                if not os.path.exists(file_path):
                    raise ArchiveError(f"File not found: {file_path}")
            
            if archive_type == 'zip':
                self._create_zip(files, archive_path)
            elif archive_type in ['tar', 'tar.gz', 'tgz']:
                self._create_tar(files, archive_path)
            else:
                raise ArchiveError(f"Unsupported archive type: {archive_type}")
            
            return archive_path
            
        except Exception as e:
            if isinstance(e, ArchiveError):
                raise
            raise ArchiveError(f"Create archive failed: {e}")
    
    def extract_archive(self, archive_path, destination=None, extract_all=True):
        """Extract archive contents"""
        try:
            validate_path(archive_path)
            
            if not os.path.exists(archive_path):
                raise ArchiveError(f"Archive not found: {archive_path}")
            
            if not destination:
                destination = os.path.dirname(archive_path)
            
            validate_path(destination)
            
            if not os.path.isdir(destination):
                raise ArchiveError(f"Destination is not a directory: {destination}")
            
            # Create extraction directory
            archive_name = os.path.splitext(os.path.basename(archive_path))[0]
            if archive_name.endswith('.tar'):
                archive_name = archive_name[:-4]
            
            extract_dir = os.path.join(destination, archive_name)
            
            # Make unique if exists
            counter = 1
            while os.path.exists(extract_dir):
                extract_dir = os.path.join(destination, f"{archive_name}_{counter}")
                counter += 1
            
            os.makedirs(extract_dir, exist_ok=True)
            
            # Extract based on file type
            if archive_path.endswith('.zip'):
                self._extract_zip(archive_path, extract_dir)
            elif archive_path.endswith(('.tar', '.tar.gz', '.tgz')):
                self._extract_tar(archive_path, extract_dir)
            else:
                raise ArchiveError(f"Unsupported archive format: {archive_path}")
            
            return extract_dir
            
        except Exception as e:
            if isinstance(e, ArchiveError):
                raise
            raise ArchiveError(f"Extract archive failed: {e}")
    
    def _create_zip(self, files, archive_path):
        """Create ZIP archive"""
        try:
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file_path in files:
                    if os.path.isfile(file_path):
                        arcname = os.path.basename(file_path)
                        zf.write(file_path, arcname)
                    elif os.path.isdir(file_path):
                        for root, dirs, walk_files in os.walk(file_path):
                            for file in walk_files:
                                full_path = os.path.join(root, file)
                                arcname = os.path.relpath(full_path, os.path.dirname(file_path))
                                zf.write(full_path, arcname)
        except Exception as e:
            raise ArchiveError(f"Create ZIP failed: {e}")
    
    def _create_tar(self, files, archive_path):
        """Create TAR archive"""
        try:
            mode = 'w:gz' if archive_path.endswith(('.tar.gz', '.tgz')) else 'w'
            with tarfile.open(archive_path, mode) as tf:
                for file_path in files:
                    arcname = os.path.basename(file_path)
                    tf.add(file_path, arcname=arcname)
        except Exception as e:
            raise ArchiveError(f"Create TAR failed: {e}")
    
    def _extract_zip(self, archive_path, destination):
        """Extract ZIP archive"""
        try:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                zf.extractall(destination)
        except Exception as e:
            raise ArchiveError(f"Extract ZIP failed: {e}")
    
    def _extract_tar(self, archive_path, destination):
        """Extract TAR archive"""
        try:
            with tarfile.open(archive_path, 'r:*') as tf:
                tf.extractall(destination)
        except Exception as e:
            raise ArchiveError(f"Extract TAR failed: {e}")
    
    def _ensure_extension(self, path, archive_type):
        """Ensure archive has correct extension"""
        ext_map = {'zip': '.zip', 'tar': '.tar', 'tar.gz': '.tar.gz', 'tgz': '.tgz'}
        ext = ext_map.get(archive_type)
        if not ext:
            return path
        if path.endswith(ext):
            return path
        # .tar.gz and .tgz are interchangeable
        if archive_type == 'tgz' and path.endswith('.tar.gz'):
            return path
        if archive_type == 'tar.gz' and path.endswith('.tgz'):
            return path
        return path + ext
    
    def list_archive(self, archive_path):
        """List contents of archive"""
        try:
            validate_path(archive_path)
            
            if not os.path.exists(archive_path):
                raise ArchiveError(f"Archive not found: {archive_path}")
            
            contents = []
            
            if archive_path.endswith('.zip'):
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    for info in zf.infolist():
                        contents.append({
                            'name': info.filename,
                            'size': info.file_size,
                            'compressed_size': info.compress_size,
                            'date': datetime(*info.date_time),
                            'is_dir': info.filename.endswith('/')
                        })
            elif archive_path.endswith(('.tar', '.tar.gz', '.tgz')):
                with tarfile.open(archive_path, 'r:*') as tf:
                    for member in tf.getmembers():
                        contents.append({
                            'name': member.name,
                            'size': member.size,
                            'date': datetime.fromtimestamp(member.mtime),
                            'is_dir': member.isdir()
                        })
            else:
                raise ArchiveError(f"Unsupported archive format: {archive_path}")
            
            return contents
            
        except ArchiveError:
            raise
        except Exception as e:
            raise ArchiveError(f"List archive failed: {e}")
    
    def test_archive(self, archive_path):
        """Test archive integrity"""
        try:
            validate_path(archive_path)
            
            if not os.path.exists(archive_path):
                raise ArchiveError(f"Archive not found: {archive_path}")
            
            if archive_path.endswith('.zip'):
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    return zf.testzip() is None
            elif archive_path.endswith(('.tar', '.tar.gz', '.tgz')):
                with tarfile.open(archive_path, 'r:*') as tf:
                    # Tar files don't have a test method, just try to read
                    tf.getmembers()
                    return True
            else:
                raise ArchiveError(f"Unsupported archive format: {archive_path}")
            
        except Exception as e:
            raise ArchiveError(f"Test archive failed: {e}")