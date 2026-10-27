"""PROTOCOL_V3 amendment 29: an execution-only real-money pilot, kept outside lab/ (lab/ never imports it).

It measures what real spot trades cost (fee, slippage against the mid at send time, maker fill rate) against the paper
model; it never claims profit. Dry mode (the default) simulates fills against live public books and logs them. Live
mode refuses unless every condition of amendment 29 point 9 holds, including the user's same-day confirmation typed
in a terminal (`python3 -m pilot confirm-today`)."""
import os

CAPITAL_USDT = 100.0
LOSS_CAP_USDT = 15.0
LOSS_BUFFER_USDT = 0.40                 # stop before the next round could cross the cap
MAX_ORDER_USDT = 20.0
ROUND_USDT = 15.0
MAX_ROUNDS = 80
MAX_LIVE_DAYS = 5
SYMBOLS = ("BTCUSDT", "ETHUSDT", "EPICUSDT", "XTZUSDT", "VETUSDT", "MITOUSDT", "HOTUSDT")
HOLD_S, MAKER_TIMEOUT_S, POLL_S = 60, 30, 2
MIN_GAP_S, MAX_GAP_S = 30 * 60, 120 * 60
MAX_SKEW_MS, MAX_SPREAD = 1000, 0.005
DRY_MIN_ROUNDS, DRY_MIN_HOURS = 20, 48
DRY_FEE = 0.001                         # Binance spot standard fee, assumed in dry mode only

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data", "pilot")
KEY_PATH = os.path.expanduser("~/.config/copybot-pilot/key.json")
TERMS_DOC = os.path.join(HERE, "research", "PILOT_VILKAAR_SKAT.md")
CONFIRM_PHRASE = "JEG BEKRÆFTER RIGTIGE PENGE I DAG"
RESUME_PHRASE = "GENOPTAG PILOTEN"
