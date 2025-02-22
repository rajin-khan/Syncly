from abc import ABC, abstractmethod

#abstract class for file upload,split,download,merge,search
class FileHandler(ABC):
    
    @abstractmethod
    def upload_file(self, file_path: str, file_name: str, mimetype: str):
        pass

    @abstractmethod
    def upload_chunk(self, service, chunk_filename: str, mimetype: str, file_name: str, chunk_index: int):
        pass

    @abstractmethod
    def update_metadata(self, metadata: str):
        pass
    
    @abstractmethod
    def download_file(self, file_id:str, save_path:str):
        pass
    
    @abstractmethod
    def search_file():
        pass
    
    @abstractmethod
    def merge_chunks(self,file_paths:str, merged_file_path:str):
        pass
    
    @abstractmethod
    def download_and_merge_chunks(self, file_name:str, save_path:str):
        pass

    @abstractmethod
    def download_from_all_buckets(self, file_name:str, save_path:str):
        pass
    