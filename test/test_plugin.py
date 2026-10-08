import pytest

from qsys_mock import Plugin


@pytest.fixture
def plugin():
    return Plugin()


def rgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def set_level(controls, ch, db):
    controls[f"level_{ch}"].Value = db


# ---------------------------------------------------------------- design time

@pytest.mark.parametrize("channels", [1, 8, 64])
@pytest.mark.parametrize("shape", ["Round", "Square"])
def test_every_layout_key_is_a_control(plugin, channels, shape):
    for page in (1, 2):
        props = plugin.props(page_index=page, Channels=channels, LED_Shape=shape)
        names = {c.Name for c in plugin.controls(props)}
        layout, _ = plugin.layout(props)
        assert set(layout) <= names


@pytest.mark.parametrize("size", [12, 36, 128])
def test_leds_and_names_do_not_overlap(plugin, size):
    props = plugin.props(Channels=4, LED_Size=size)
    layout, _ = plugin.layout(props)
    rects = [(v.Position[1], v.Position[2], v.Size[1], v.Size[2]) for v in layout.values()]
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            overlap = (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
                       and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])
            assert not overlap, (a, b)


def test_round_led_is_a_circle(plugin):
    layout, _ = plugin.layout(plugin.props(Channels=1, LED_Size=36))
    assert layout["led_1"].CornerRadius == 18


# ------------------------------------------------------------------- runtime

def test_silence_turns_led_off(plugin):
    c = plugin.boot(Channels=1)
    set_level(c, 1, -100)
    plugin.tick()
    assert c.led_1.Boolean is False


def test_low_level_is_blue_and_top_is_red(plugin):
    c = plugin.boot(Channels=2)
    set_level(c, 1, -47)   # just above the default -48 floor
    set_level(c, 2, 6)     # past the 0 dB top of the range
    plugin.tick()
    r, g, b = rgb(c.led_1.Color)
    assert c.led_1.Boolean and b > 200 and r < 20
    assert c.led_2.Boolean and rgb(c.led_2.Color) == (255, 0, 0)


def test_color_moves_through_the_gradient(plugin):
    c = plugin.boot(Channels=1)
    reds = []
    for db in (-40, -24, -12, -6, -2, 0):
        set_level(c, 1, db)
        plugin.tick()
        reds.append(rgb(c.led_1.Color)[0])
    assert reds == sorted(reds) and reds[0] < reds[-1]


def test_release_fades_color_back_down(plugin):
    c = plugin.boot(Channels=1)
    set_level(c, 1, 0)
    plugin.tick()
    set_level(c, 1, -100)
    plugin.tick()           # 20 dB/s * 0.05 s = 1 dB fall -> still nearly red
    r1 = rgb(c.led_1.Color)[0]
    assert c.led_1.Boolean and r1 > 200
    plugin.tick(20)         # ~21 dB down after a second
    assert rgb(c.led_1.Color)[0] < r1
    plugin.tick(60)         # long gone
    assert c.led_1.Boolean is False


def test_range_properties_rescale_colors(plugin):
    c = plugin.boot(Channels=1, overrides={"Off Below (dB)": -20, "Full Red At (dB)": -10})
    set_level(c, 1, -21)
    plugin.tick()
    assert c.led_1.Boolean is False
    set_level(c, 1, -10)
    plugin.tick()
    assert rgb(c.led_1.Color) == (255, 0, 0)


def test_mid_level_is_not_red_with_default_properties(plugin):
    # Regression: in Designer the LED stayed red because the range and release
    # knobs started at their Min values instead of their intended defaults.
    c = plugin.boot(Channels=1)
    set_level(c, 1, -30)
    plugin.tick()
    r, g, b = rgb(c.led_1.Color)
    assert b > r


def test_color_recovers_quickly_after_a_peak(plugin):
    c = plugin.boot(Channels=1)
    set_level(c, 1, 20)
    plugin.tick()
    set_level(c, 1, -30)
    plugin.tick(60)         # 3 s at 20 dB/s is 60 dB, back down to -30
    r, g, b = rgb(c.led_1.Color)
    assert b > r


def test_release_property_sets_fall_rate(plugin):
    c = plugin.boot(Channels=1, overrides={"Release (dB/s)": 200})
    set_level(c, 1, 0)
    plugin.tick()
    set_level(c, 1, -100)
    plugin.tick(5)          # 200 dB/s * 0.25 s = 50 dB, below the -48 floor
    assert c.led_1.Boolean is False


def test_named_component_source(plugin):
    c = plugin.boot(Channels=1, components={"Mic1": {"meter.1": 0}})
    c.comp_1.String = "Mic1"
    c.ctrl_1.String = "meter.1"
    c.comp_1.EventHandler(c.comp_1)
    set_level(c, 1, -100)   # pin is ignored once a component is bound
    plugin.tick()
    assert rgb(c.led_1.Color) == (255, 0, 0)
    assert c.Status.Value == 0


def test_missing_component_reports_fault(plugin):
    c = plugin.boot(Channels=2)
    c.comp_2.String = "Nope"
    c.ctrl_2.String = "meter.1"
    c.ctrl_2.EventHandler(c.ctrl_2)
    assert c.Status.Value == 2
    assert "Ch 2" in c.Status.String
    plugin.tick()  # falls back to the pin, must not error


def test_color_sweep_ignores_input(plugin):
    c = plugin.boot(Channels=2, overrides={"Diagnostics": "Color Sweep"})
    set_level(c, 1, -100)
    seen = set()
    for _ in range(80):
        plugin.tick()
        seen.add(c.led_2.Color)
    assert c.led_1.Boolean and len(seen) > 40
    assert "#FF0000" in seen


def test_log_mode_runs(plugin):
    c = plugin.boot(Channels=2, overrides={"Diagnostics": "Log"})
    set_level(c, 1, -10)
    plugin.tick(40)
    assert c.led_1.Boolean


def test_runtime_error_is_reported_not_fatal(plugin):
    c = plugin.boot(Channels=1)
    plugin.lua.execute("Controls.level_1.Value = nil")
    plugin.tick()
    assert c.Status.Value == 2 and "Script error" in c.Status.String
