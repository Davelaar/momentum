
from momentum.models.intent import Intent, TakeProfitLeg
from momentum.utils.safety import SafetyKnobs
from momentum.exchange.kraken.ws_v2_payloads import build_primary_payload, build_standalone_tp_messages

def test_build_limit_with_oto_sl():
    intent = Intent(symbol="BTC/USD", side="buy", qty=0.001, order_type="limit", limit_price=28440,
                    oto_order_type="stop-loss-limit", oto_trigger_price=28410, oto_limit_price=28400)
    knobs = SafetyKnobs(entry_max_notional=100000, one_position_only=0, abs_limit_required=1)
    msg = build_primary_payload(intent, "USD", knobs, token_placeholder="TOKEN")
    p = msg.model_dump()["params"]
    assert p["order_type"] == "limit"
    assert p["conditional"]["order_type"] == "stop-loss-limit"
    assert p["conditional"]["trigger_price"] == 28410
    assert p["conditional"]["limit_price"] == 28400

def test_build_standalone_tp():
    legs = [TakeProfitLeg(trigger_price=28600, limit_price=28590, pct_size=1.0)]
    knobs = SafetyKnobs(entry_max_notional=100000, one_position_only=0, abs_limit_required=1)
    msgs = build_standalone_tp_messages("BTC/USD","sell",0.001,legs,"USD",knobs,token_placeholder="TOKEN")
    p = msgs[0].model_dump()["params"]
    assert p["order_type"] == "take-profit-limit"
    assert p["triggers"]["price"] == 28600
    assert p["limit_price"] == 28590
