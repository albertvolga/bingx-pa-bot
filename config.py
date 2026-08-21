import os
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BINGX_API_KEY = os.getenv("BINGX_API_KEY", "")
BINGX_SECRET_KEY = os.getenv("BINGX_SECRET_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Маппинг символов для BingX
SYMBOL_MAP = {
    "BTC": "BTC-USDT",
    "ETH": "ETH-USDT",
    "BNB": "BNB-USDT",
    "SOL": "SOL-USDT",
    "XRP": "XRP-USDT",
    "ADA": "ADA-USDT",
    "DOGE": "DOGE-USDT",
    "TON": "TON-USDT",
    "SHIB": "SHIB-USDT",
    "DOT": "DOT-USDT",
    "TRX": "TRX-USDT",
    "AVAX": "AVAX-USDT",
    "LINK": "LINK-USDT",
    "BCH": "BCH-USDT",
    "UNI": "UNI-USDT",
    "ICP": "ICP-USDT",
    "NEAR": "NEAR-USDT",
    "ETC": "ETC-USDT",
    "ATOM": "ATOM-USDT",
    "IMX": "IMX-USDT",
    "OP": "OP-USDT",
    "ARB": "ARB-USDT",
    "APT": "APT-USDT",
    "HBAR": "HBAR-USDT",
    "GRT": "GRT-USDT",
    "GALA": "GALA-USDT",
    "TIA": "TIA-USDT",
    "FLOKI": "FLOKI-USDT",
    "PEPE": "PEPE-USDT",
    "WIF": "WIF-USDT",
    "KAS": "KAS-USDT",
    "BONK": "BONK-USDT",
    "ORDI": "ORDI-USDT",
    "SUI": "SUI-USDT",
    "SEI": "SEI-USDT",
    "ONDO": "ONDO-USDT",
    "WLD": "WLD-USDT",
    "ENJ": "ENJ-USDT",
    "AXS": "AXS-USDT",
    "MANTA": "MANTA-USDT",
    "FET": "FET-USDT",
    "AGIX": "AGIX-USDT",
    "RNDR": "RNDR-USDT",
    "INJ": "INJ-USDT",
    "OCEAN": "OCEAN-USDT",
    "ALGO": "ALGO-USDT",
    "FTM": "FTM-USDT",
    "SAND": "SAND-USDT",
    "CHZ": "CHZ-USDT",
    "DYDX": "DYDX-USDT",
    "PYTH": "PYTH-USDT",
    "MEME": "MEME-USDT",
    "JUP": "JUP-USDT",
    "JTO": "JTO-USDT",
    "STRK": "STRK-USDT",
    "MINA": "MINA-USDT",
    "ETHFI": "ETHFI-USDT",
    "RUNE": "RUNE-USDT",
    "ROSE": "ROSE-USDT",
    "WOO": "WOO-USDT",
    "ZRX": "ZRX-USDT",
    "AR": "AR-USDT",
    "ENS": "ENS-USDT",
    "AAVE": "AAVE-USDT",
    "OMG": "OMG-USDT",
    "ENA": "ENA-USDT",
    "W": "W-USDT",
    "FIL": "FIL-USDT",
    "GRT": "GRT-USDT",
    "CELO": "CELO-USDT",
    "STX": "STX-USDT",
    "BOME": "BOME-USDT",
    "ZETA": "ZETA-USDT",
    "REZ": "REZ-USDT",
    "AEVO": "AEVO-USDT",
    "CORE": "CORE-USDT",
    "NOT": "NOT-USDT",
    "FLR": "FLR-USDT",
    "IO": "IO-USDT",
    "ZK": "ZK-USDT",
    "LISTA": "LISTA-USDT",
    "BB": "BB-USDT",
    "PRIME": "PRIME-USDT",
    "HIGH": "HIGH-USDT",
    "LTC": "LTC-USDT",
    "APT": "APT-USDT", # Дубликат, но не критично
    "SXP": "SXP-USDT",
    "1000PEPE": "1000PEPE-USDT",
    "1000BONK": "1000BONK-USDT",
    "1000FLOKI": "1000FLOKI-USDT",
    "1000SHIB": "1000SHIB-USDT",
    "WEMIX": "WEMIX-USDT",
    "PYTH": "PYTH-USDT", # Дубликат
    "SNX": "SNX-USDT",
    "JTO": "JTO-USDT", # Дубликат
    "RSR": "RSR-USDT",
    "KNC": "KNC-USDT",
    "OCEAN": "OCEAN-USDT", # Дубликат
    "ZIL": "ZIL-USDT",
    "LPT": "LPT-USDT",
    "JASMY": "JASMY-USDT",
    "RAY": "RAY-USDT",
    "PHA": "PHA-USDT",
    "CVC": "CVC-USDT",
    "DGB": "DGB-USDT",
    "SYS": "SYS-USDT",
    "SSV": "SSV-USDT",
    "NFP": "NFP-USDT",
    "CTK": "CTK-USDT",
    "UMA": "UMA-USDT",
    "LEO": "LEO-USDT", # USDT-LEO - Binance, а тут надо LEO-USDT (если есть)
    "PENDLE": "PENDLE-USDT",
    "ENA": "ENA-USDT", # Дубликат
    "W": "W-USDT", # Дубликат
    "DEGEN": "DEGEN-USDT",
    "CRV": "CRV-USDT",
    "COMP": "COMP-USDT",
    "HOOK": "HOOK-USDT",
    "MAVIA": "MAVIA-USDT",
    "PDA": "PDA-USDT",
    "GNS": "GNS-USDT",
    "GLMR": "GLMR-USDT",
    "JOE": "JOE-USDT",
    "XVG": "XVG-USDT",
    "FRONT": "FRONT-USDT",
    "DUSK": "DUSK-USDT",
    "FET": "FET-USDT", # Дубликат
    "AGIX": "AGIX-USDT", # Дубликат
    "OCEAN": "OCEAN-USDT", # Дубликат
    "ARKM": "ARKM-USDT",
    "AR": "AR-USDT", # Дубликат
    "TRB": "TRB-USDT",
    "PERP": "PERP-USDT",
    "FXS": "FXS-USDT",
    "GTC": "GTC-USDT",
    "STG": "STG-USDT",
    "CYBER": "CYBER-USDT",
    "BLZ": "BLZ-USDT",
    "CFX": "CFX-USDT",
    "API3": "API3-USDT",
    "RDNT": "RDNT-USDT",
    "GAL": "GAL-USDT",
    "BADGER": "BADGER-USDT",
    "CELR": "CELR-USDT",
    "POND": "POND-USDT",
    "SFP": "SFP-USDT",
    "LINA": "LINA-USDT",
    "NMR": "NMR-USDT",
    "VTHO": "VTHO-USDT",
    "ARDR": "ARDR-USDT",
    "REQ": "REQ-USDT",
    "POWR": "POWR-USDT",
    "CTSI": "CTSI-USDT",
    "ID": "ID-USDT",
    "HOOK": "HOOK-USDT", # Дубликат
    "MAVIA": "MAVIA-USDT", # Дубликат
    "PDA": "PDA-USDT", # Дубликат
    "GNS": "GNS-USDT", # Дубликат
    "GLMR": "GLMR-USDT", # Дубликат
    "JOE": "JOE-USDT", # Дубликат
    "XVG": "XVG-USDT", # Дубликат
    "FRONT": "FRONT-USDT", # Дубликат
    "DUSK": "DUSK-USDT" # Дубликат
}

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Ошибка: TELEGRAM_BOT_TOKEN не найден в .env файле!")
