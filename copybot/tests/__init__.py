"""Order 73: no ordinary test may open a file in the quarantine register."""
from tests import offline_market

offline_market.install_quarantine_guard()
