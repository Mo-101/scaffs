import pytest
import sys
from pathlib import Path

agent_dir = Path(__file__).resolve().parent.parent
backend_dir = agent_dir.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(agent_dir))
sys.path.insert(0, str(agent_dir / "src"))

def test_paper_engine_imports():
    import paper_session
    import futures_paper_engine
    import bounded_grid_strategy
    import morning_glory_strategy
    import many_bots_futures_adapter
    import migration
    import paper_postgres
    import paper_accounting_guard
    assert paper_session is not None
    assert futures_paper_engine is not None
    assert bounded_grid_strategy is not None
    assert morning_glory_strategy is not None

def test_routes_imports():
    import api.paper_session_routes
    import api.system_routes
    import api.idimikang_routes
    assert api.paper_session_routes is not None
    assert api.system_routes is not None
    assert api.idimikang_routes is not None

def test_futures_paper_engine_basic():
    from futures_paper_engine import normalize_symbol
    assert normalize_symbol("BTC/USDT") == "BTCUSDT"
    assert normalize_symbol("BTC-USDT") == "BTCUSDT"
    assert normalize_symbol("BTCUSDT") == "BTCUSDT"
