from ai_layer.application import action_engine, action_state


def test_action_engine_reexports_public_protocol_after_state_seam_extraction() -> None:
    assert action_engine.ActionProtocolError is action_state.ActionProtocolError
    assert action_engine.action_token_shape_valid is action_state.action_token_shape_valid
    assert action_engine.report_fingerprint is action_state.report_fingerprint
    assert action_engine.action_debug_snapshot is action_state.action_debug_snapshot
