#import libraries for abstraction
from abc import ABC, abstractmethod


class service(ABC):
    #abstract methods for service classes
    @abstractmethod
    def authenticate(self, bucket_numer: int):
        pass

    @abstractmethod
    def list_files(self, max_results: int = None, query: str = None):
        pass

    @abstractmethod
    def upload_chunk(self, chunk_path:str, file_name: str, mimetype: str,chunk_index: int):
        pass
    
    @abstractmethod
    def upload_file(self, file_path:str, file_name: str, mimetype: str):
        pass

    @abstractmethod
    def download_file(self, file_id: str, save_path: str):
        pass

    @abstractmethod
    def check_storage(self):
        pass