"""Minimal mock of the Q-SYS Lua environment for exercising a .qplug off-Core.

Loads the plugin into a Lua runtime (via lupa), exposes the design-time
functions, and can boot the runtime section with fake Controls, Properties,
Component and Timer objects.
"""
from pathlib import Path

from lupa import LuaRuntime

PLUGIN = Path(__file__).resolve().parent.parent / "SQ-Style LED Meter.qplug"

MOCK_LUA = r"""
local function newControl(def)
  -- Designer ignores DefaultValue in plugin control definitions: knobs start
  -- at their Min, so the mock does too (that bug shipped once already).
  local c = { Name = def.Name, Value = def.Min or 0, String = "",
              Boolean = false, Color = nil, EventHandler = nil }
  if type(c.Value) == "boolean" then c.Boolean = c.Value; c.Value = c.Boolean and 1 or 0 end
  if def.ControlType == "Button" then c.Boolean = (c.Value ~= 0) end
  return c
end

function MockBoot(controlDefs, props, components)
  Controls = {}
  for _, d in ipairs(controlDefs) do Controls[d.Name] = newControl(d) end
  Properties = props
  -- Weak table: like Q-SYS, a timer the script doesn't keep a reference to
  -- gets garbage collected and stops firing.
  MockTimers = setmetatable({}, { __mode = "v" })
  Timer = { New = function()
    local t = { EventHandler = nil, rate = nil }
    function t:Start(r) self.rate = r end
    function t:Stop() self.rate = nil end
    table.insert(MockTimers, t)
    return t
  end }
  Component = { New = function(name)
    local comp = components[name]
    if not comp then return setmetatable({}, { __index = function() return nil end }) end
    return comp
  end }
end

function MockTick(n)
  collectgarbage("collect")
  for _ = 1, n or 1 do
    for _, t in pairs(MockTimers) do
      if t and t.rate and t.EventHandler then t.EventHandler(t) end
    end
  end
end
"""


class Plugin:
    def __init__(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MOCK_LUA)
        self.src = PLUGIN.read_text()
        self.lua.execute(self.src)
        self.g = self.lua.globals()

    def props(self, page_index=1, overrides=None, **kw):
        """Default properties; override by exact name in `overrides`, or by
        keyword with underscores for spaces (Channels=4, LED_Size=24)."""
        props = self.lua.table()
        for p in self.g.GetProperties().values():
            entry = self.lua.table(Value=p.Value)
            props[p.Name] = entry
        named = {k.replace("_", " "): v for k, v in kw.items()}
        named.update(overrides or {})
        for k, v in named.items():
            assert props[k] is not None, f"no property {k!r}"
            props[k].Value = v
        props["page_index"] = self.lua.table(Value=page_index)
        return props

    def controls(self, props):
        return list(self.g.GetControls(props).values())

    def layout(self, props):
        layout, graphics = self.g.GetControlLayout(props)
        return dict(layout.items()), list(graphics.values())

    def boot(self, components=None, overrides=None, **kw):
        """Run the plugin's runtime section with mocked Q-SYS globals."""
        props = self.props(overrides=overrides, **kw)
        comps = self.lua.table()
        for name, ctrls in (components or {}).items():
            t = self.lua.table()
            for cname, value in ctrls.items():
                t[cname] = self.lua.table(Value=value)
            comps[name] = t
        self.g.MockBoot(self.g.GetControls(props), props, comps)
        self.lua.execute(self.src)  # Controls is now set, so the runtime block runs
        return self.g.Controls

    def tick(self, n=1):
        self.g.MockTick(n)
