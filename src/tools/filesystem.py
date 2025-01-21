"""
File system operations for Anthropic CLI tools.
"""
import os
from pathlib import Path
from typing import List, Optional, Union

class FileSystemTools:
    """Tools for file system operations."""
    
    @staticmethod
    def read_file(file_path: Union[str, Path], encoding: str = 'utf-8') -> str:
        """
        Read contents of a file.
        
        Args:
            file_path: Path to the file
            encoding: File encoding (default: utf-8)
            
        Returns:
            str: Contents of the file
            
        Raises:
            FileNotFoundError: If file doesn't exist
            IOError: If file can't be read
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        try:
            with open(path, 'r', encoding=encoding) as f:
                return f.read()
        except IOError as e:
            raise IOError(f"Error reading file {file_path}: {str(e)}")
    
    @staticmethod
    def write_file(
        file_path: Union[str, Path],
        content: str,
        encoding: str = 'utf-8',
        create_dirs: bool = True
    ) -> None:
        """
        Write content to a file.
        
        Args:
            file_path: Path to the file
            content: Content to write
            encoding: File encoding (default: utf-8)
            create_dirs: Create parent directories if they don't exist
            
        Raises:
            IOError: If file can't be written
        """
        path = Path(file_path)
        
        if create_dirs:
            path.parent.mkdir(parents=True, exist_ok=True)
            
        try:
            with open(path, 'w', encoding=encoding) as f:
                f.write(content)
        except IOError as e:
            raise IOError(f"Error writing to file {file_path}: {str(e)}")
    
    @staticmethod
    def list_directory(
        directory: Union[str, Path],
        pattern: Optional[str] = None,
        recursive: bool = False
    ) -> List[Path]:
        """
        List contents of a directory.
        
        Args:
            directory: Path to the directory
            pattern: Optional glob pattern to filter files
            recursive: Whether to list subdirectories recursively
            
        Returns:
            List[Path]: List of paths in the directory
            
        Raises:
            NotADirectoryError: If path is not a directory
            FileNotFoundError: If directory doesn't exist
        """
        path = Path(directory)
        
        if not path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")
        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: {directory}")
            
        try:
            if recursive:
                if pattern:
                    return list(path.rglob(pattern))
                return list(path.rglob("*"))
            else:
                if pattern:
                    return list(path.glob(pattern))
                return list(path.glob("*"))
        except Exception as e:
            raise IOError(f"Error listing directory {directory}: {str(e)}") 