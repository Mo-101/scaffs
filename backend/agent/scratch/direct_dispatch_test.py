import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent.parent
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from src.trading.signal_queue import SignalQueueManager

mgr = SignalQueueManager()
pending = mgr.get_pending_batch(limit=1)
if pending:
    sig = pending[0]
    print(f"Direct dispatch testing signal: {sig['id']} {sig['symbol']} {sig['side']}")
    try:
        res = mgr.dispatch_queued_signal(sig["id"], notional_usd=25.0)
        print("Dispatch result:", res)
    except Exception as e:
        import traceback
        traceback.print_exc()
