# --- START OF FILE Service.py ---

#import libraries for abstraction
from abc import ABC, abstractmethod
from typing import List, Dict, Optional # Added typing imports

class Service(ABC):
    #abstract methods for service classes
    @abstractmethod
    def authenticate(self, bucket_number: int, user_id): # Added user_id type hint later if available
        pass

    @abstractmethod
    def listFiles(self, max_results: Optional[int] = None, query: Optional[str] = None) -> List[Dict]: # Added return type hint
        pass

    @abstractmethod
    def check_storage(self) -> tuple[int, int]: # Added return type hint
        pass

    # --- New Abstract Method ---
    @abstractmethod
    def searchFiles(self, query: str, limit: int = 10) -> List[Dict]:
        """Searches for files matching the query string."""
        pass
# --- END OF FILE Service.py ---