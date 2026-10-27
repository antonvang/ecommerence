"""PROTOCOL_V3 amendments 29/29a: the execution pilot, kept outside lab/ (lab/ never imports it), research and paper
only (29a, the user's decision B): rounds are simulated against live public order books with hard stops; no account,
key or order code exists. It never claims profit."""
import os

CAPITAL_USDT = 100.0
LOSS_CAP_USDT = 15.0
LOSS_BUFFER_USDT = 0.40                 # stop before the next round could cross the cap
MAX_ORDER_USDT = 20.0
ROUND_USDT = 15.0
MAX_ROUNDS = 80
SYMBOLS = ("BTCUSDT", "ETHUSDT", "EPICUSDT", "XTZUSDT", "VETUSDT", "MITOUSDT", "HOTUSDT")
HOLD_S, MAKER_TIMEOUT_S, POLL_S = 60, 30, 2
MIN_GAP_S, MAX_GAP_S = 30 * 60, 120 * 60
MAX_SKEW_MS, MAX_SPREAD = 1000, 0.005
DRY_MIN_ROUNDS, DRY_MIN_HOURS = 20, 48
DRY_FEE = 0.001                         # Binance spot standard fee, assumed in dry mode only

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data", "pilot")
RESUME_PHRASE = "GENOPTAG PILOTEN"
