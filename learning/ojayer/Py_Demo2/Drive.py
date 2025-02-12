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
    def check_storage(self):
        pass
