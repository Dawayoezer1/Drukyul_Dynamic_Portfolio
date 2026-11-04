from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
CACHE = ROOT / '.cache'
KEYS = {'eodhd': os.getenv('EODHD_API_KEY', ''),
        'twelve': os.getenv('TWELVE_DATA_API_KEY', '')}

# Dynamic strategy tuning
REBALANCE_EVERY = 21      # trading days (monthly)
LOOKBACK = 252
NO_TRADE_BAND = 0.05
TURNOVER_LAMBDA = 0.02
RETURN_SHRINK = 0.7
W_MAX = 0.30\

BLEND = 0.3 

@dataclass(frozen=True)
class Settings:
    capital: float = 100000.0
    lookback: int = 126
    gamma: float = 2.0  
    cap: float = 1.0
    frequency: str = 'Monthly'
    risk_free: float = 0.03
    mar: float = 0.0
    max_gap_days: int = 10
    
