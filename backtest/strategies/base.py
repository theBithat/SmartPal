"""Base class for all strategies."""
import pandas as pd
from abc import ABC, abstractmethod
from dataclasses import dataclass


class Strategy(ABC):
    """
    Override generate_signals() to return a DataFrame with boolean columns:
      long_entry, long_exit, short_entry, short_exit
    """
    name: str = "unnamed"

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """df has columns: open, high, low, close, volume"""
        ...

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name})"
