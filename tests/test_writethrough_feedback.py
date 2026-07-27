"""Write-through context filtering tests."""

from types import SimpleNamespace

from custom_components.overlay_scenes.writethrough import WriteThroughHandler


def test_own_context_and_child_context_are_ignored() -> None:
    loop = SimpleNamespace(call_later=lambda *args: SimpleNamespace(cancel=lambda: None))
    handler = WriteThroughHandler(SimpleNamespace(loop=loop))
    handler._remember("ours")
    assert handler.should_ignore(SimpleNamespace(context=SimpleNamespace(id="ours", parent_id=None)))
    assert handler.should_ignore(SimpleNamespace(context=SimpleNamespace(id="child", parent_id="ours")))
    assert not handler.should_ignore(SimpleNamespace(context=SimpleNamespace(id="external", parent_id=None)))
