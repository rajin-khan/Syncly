#import libraries for abstraction
from abc import ABC, abstractmethod


class Service(ABC):
    #abstract methods for service classes
    @abstractmethod
    def authenticate(self, bucket_number: int):
        pass

    @abstractmethod
    def listFiles(self, max_results: int = None, query: str = None):
        pass

    @abstractmethod
    def check_storage(self):
        pass
