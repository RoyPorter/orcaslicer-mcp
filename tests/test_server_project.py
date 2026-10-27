import json
import httpx, respx
import orcaslicer_mcp.server as srv
from orcaslicer_mcp.client import OrcaClient
from orcaslicer_mcp.config import load_config


def _env(m):
    m.setenv("ORCA_API_TOKEN", "tok"); m.setenv("ORCA_API_URL", "http://x:13130")


_PROJECT = {"name": "float_spinner", "path": "/u/float_spinner.3mf", "saved": True,
            "dirty": False, "plates": 4, "objects": 9}


# --- get_status: project folded into {name, path, dirty} -------------------------------

@respx.mock
async def test_get_status_folds_project_fields(monkeypatch):
    _env(monkeypatch)
    respx.get("http://x:13130/api/v1/status").mock(return_value=httpx.Response(200, json={
        "app": "OrcaSlicer", "project": "/u/float_spinner.3mf", "project_name": "float_spinner",
        "project_dirty": True, "presets": {"filaments": ["A"], "print": "P", "printer": "M"}}))
    out = await srv.get_status()
    assert out["project"] == {"name": "float_spinner", "path": "/u/float_spinner.3mf", "dirty": True}
    assert "project_name" not in out and "project_dirty" not in out


@respx.mock
async def test_get_status_old_build_keeps_project_string(monkeypatch):
    _env(monkeypatch)
    respx.get("http://x:13130/api/v1/status").mock(return_value=httpx.Response(200, json={
        "app": "OrcaSlicer", "project": "", "presets": {"filaments": [], "print": "P", "printer": "M"}}))
    out = await srv.get_status()
    assert out["project"] == ""


@respx.mock
async def test_get_status_unsaved_project_has_empty_path(monkeypatch):
    _env(monkeypatch)
    respx.get("http://x:13130/api/v1/status").mock(return_value=httpx.Response(200, json={
        "app": "OrcaSlicer", "project": "", "project_name": "Untitled", "project_dirty": False}))
    async with OrcaClient(load_config()) as c:
        out = await c.get_status()
    assert out["project"] == {"name": "Untitled", "path": "", "dirty": False}


# --- save_project ----------------------------------------------------------------------

@respx.mock
async def test_save_project_default_saves_to_own_path(monkeypatch):
    _env(monkeypatch)
    route = respx.post("http://x:13130/api/v1/project/save").mock(return_value=httpx.Response(200, json={
        "saved": "/u/float_spinner.3mf", "bytes": 1834021, "project": _PROJECT}))
    out = await srv.save_project()
    assert out["saved"] == "/u/float_spinner.3mf" and out["bytes"] == 1834021
    assert json.loads(route.calls.last.request.content) == {"path": None, "overwrite": False}


@respx.mock
async def test_save_project_as_sends_path_and_overwrite(monkeypatch):
    _env(monkeypatch)
    route = respx.post("http://x:13130/api/v1/project/save").mock(return_value=httpx.Response(200, json={
        "saved": "/u/b.3mf", "bytes": 10, "project": dict(_PROJECT, path="/u/b.3mf")}))
    await srv.save_project("/u/b.3mf", overwrite=True)
    assert json.loads(route.calls.last.request.content) == {"path": "/u/b.3mf", "overwrite": True}


@respx.mock
async def test_save_project_never_saved_422(monkeypatch):
    _env(monkeypatch)
    respx.post("http://x:13130/api/v1/project/save").mock(return_value=httpx.Response(422, json={
        "error": "no_project_path", "detail": "the project has never been saved; pass a path"}))
    out = await srv.save_project()
    assert out["error"] == "no_project_path"


@respx.mock
async def test_save_project_exists_409_passes_through(monkeypatch):
    _env(monkeypatch)
    respx.post("http://x:13130/api/v1/project/save").mock(return_value=httpx.Response(409, json={
        "error": "exists", "path": "/u/b.3mf"}))
    out = await srv.save_project("/u/b.3mf")
    assert out["error"] == "exists"


@respx.mock
async def test_save_project_needs_project_build(monkeypatch):
    _env(monkeypatch)
    respx.post("http://x:13130/api/v1/project/save").mock(return_value=httpx.Response(404, json={"error": "not_found"}))
    out = await srv.save_project()
    assert "fork v2.4.2-mcp.14" in out["error"]


# --- open_project / new_project --------------------------------------------------------

@respx.mock
async def test_open_project_defaults(monkeypatch):
    _env(monkeypatch)
    route = respx.post("http://x:13130/api/v1/project/open").mock(return_value=httpx.Response(200, json={
        "opened": "/u/float_spinner.3mf", "plates": 4, "objects": 9, "had_unsaved_changes": False,
        "discarded_changes": [], "project": _PROJECT}))
    out = await srv.open_project("/u/float_spinner.3mf")
    assert out["opened"] == "/u/float_spinner.3mf" and out["plates"] == 4
    assert json.loads(route.calls.last.request.content) == {
        "path": "/u/float_spinner.3mf", "if_unsaved": "fail", "presets": "project"}


@respx.mock
async def test_open_project_passes_choices(monkeypatch):
    _env(monkeypatch)
    route = respx.post("http://x:13130/api/v1/project/open").mock(return_value=httpx.Response(200, json={
        "opened": "/u/a.3mf", "plates": 1, "objects": 0, "had_unsaved_changes": True,
        "saved": "/u/old.3mf", "discarded_changes": ["print"], "presets_restored": ["filament"],
        "project": _PROJECT}))
    out = await srv.open_project("/u/a.3mf", if_unsaved="save", presets="keep_current")
    assert out["saved"] == "/u/old.3mf" and out["presets_restored"] == ["filament"]
    assert json.loads(route.calls.last.request.content) == {
        "path": "/u/a.3mf", "if_unsaved": "save", "presets": "keep_current"}


@respx.mock
async def test_open_project_unsaved_changes_is_not_a_capability_gap(monkeypatch):
    _env(monkeypatch)
    respx.post("http://x:13130/api/v1/project/open").mock(return_value=httpx.Response(422, json={
        "error": "unsaved_changes", "detail": "pass if_unsaved: \"save\" or \"discard\"",
        "modified": ["print"], "project": dict(_PROJECT, dirty=True)}))
    out = await srv.open_project("/u/a.3mf")
    assert out["error"] == "unsaved_changes"


@respx.mock
async def test_open_project_missing_file_404_keeps_message(monkeypatch):
    _env(monkeypatch)
    respx.post("http://x:13130/api/v1/project/open").mock(return_value=httpx.Response(404, json={"error": "file_not_found", "path": "/u/missing.3mf"}))
    out = await srv.open_project("/u/missing.3mf")
    assert out["error"] == "file_not_found"


@respx.mock
async def test_new_project_default_and_discard(monkeypatch):
    _env(monkeypatch)
    route = respx.post("http://x:13130/api/v1/project/new").mock(return_value=httpx.Response(200, json={
        "ok": True, "had_unsaved_changes": False, "kept_changes": [],
        "project": {"name": "Untitled", "path": "", "saved": False, "dirty": False, "plates": 1, "objects": 0}}))
    out = await srv.new_project()
    assert out["ok"] is True and out["project"]["name"] == "Untitled"
    assert json.loads(route.calls.last.request.content) == {"if_unsaved": "fail"}
    await srv.new_project(if_unsaved="discard")
    assert json.loads(route.calls.last.request.content) == {"if_unsaved": "discard"}


@respx.mock
async def test_new_project_slicing_409(monkeypatch):
    _env(monkeypatch)
    respx.post("http://x:13130/api/v1/project/new").mock(return_value=httpx.Response(409, json={"error": "slicing"}))
    out = await srv.new_project(if_unsaved="discard")
    assert out["error"] == "slicing"


# --- set_plate -------------------------------------------------------------------------

_PLATE = {"index": 2, "name": "floats", "current": False, "locked": False, "empty": False,
          "slice_result_valid": False, "bed_type": "Textured PEI Plate",
          "bed_type_effective": "Textured PEI Plate", "print_sequence": "default",
          "print_sequence_effective": "by_layer", "origin": [562, 0, 0],
          "bbox_min": [562, 0, 0], "bbox_max": [818, 256, 250], "objects": []}


@respx.mock
async def test_set_plate_sends_only_given_fields(monkeypatch):
    _env(monkeypatch)
    route = respx.patch("http://x:13130/api/v1/plates/2").mock(return_value=httpx.Response(200, json={
        "changed": ["bed_type"], "plate": _PLATE}))
    out = await srv.set_plate(2, bed_type="Textured PEI Plate")
    assert out["changed"] == ["bed_type"] and out["plate"]["bed_type"] == "Textured PEI Plate"
    assert json.loads(route.calls.last.request.content) == {"bed_type": "Textured PEI Plate"}
    await srv.set_plate(2, name="floats", print_sequence="by_object")
    assert json.loads(route.calls.last.request.content) == {"name": "floats", "print_sequence": "by_object"}


async def test_set_plate_nothing_to_set_is_local(monkeypatch):
    _env(monkeypatch)
    out = await srv.set_plate(0)
    assert out["error"] == "nothing_to_set"


@respx.mock
async def test_set_plate_unknown_bed_type_lists_allowed(monkeypatch):
    _env(monkeypatch)
    respx.patch("http://x:13130/api/v1/plates/0").mock(return_value=httpx.Response(400, json={
        "error": "unknown_bed_type", "allowed": ["default", "Cool Plate", "Engineering Plate"]}))
    out = await srv.set_plate(0, bed_type="Garolite")
    assert "unknown_bed_type" in out["error"]


@respx.mock
async def test_set_plate_unknown_plate_404(monkeypatch):
    _env(monkeypatch)
    respx.patch("http://x:13130/api/v1/plates/9").mock(return_value=httpx.Response(404, json={"error": "unknown_plate", "count": 4}))
    out = await srv.set_plate(9, name="x")
    assert out["error"] == "unknown_plate"


@respx.mock
async def test_set_plate_needs_project_build(monkeypatch):
    _env(monkeypatch)
    respx.patch("http://x:13130/api/v1/plates/0").mock(return_value=httpx.Response(404, json={"error": "not_found"}))
    out = await srv.set_plate(0, name="x")
    assert "fork v2.4.2-mcp.14" in out["error"]


# --- filament slots --------------------------------------------------------------------

@respx.mock
async def test_list_filament_slots(monkeypatch):
    _env(monkeypatch)
    respx.get("http://x:13130/api/v1/filaments").mock(return_value=httpx.Response(200, json={
        "slots": [{"slot": 1, "preset": "Generic PETG", "colour": "#FF8000", "type": "PETG", "system": True},
                  {"slot": 2, "preset": "My LW-ASA", "colour": "#808080", "type": "ASA", "system": False}],
        "count": 2}))
    out = await srv.list_filament_slots()
    assert out["count"] == 2 and out["slots"][1]["preset"] == "My LW-ASA"


@respx.mock
async def test_set_slot_filament_sends_only_given_fields(monkeypatch):
    _env(monkeypatch)
    route = respx.put("http://x:13130/api/v1/filaments/4").mock(return_value=httpx.Response(200, json={
        "slot": 4, "preset": "My LW-ASA", "colour": "#808080", "changed": ["preset", "colour"],
        "discarded_changes": []}))
    out = await srv.set_slot_filament(4, preset="My LW-ASA", colour="#808080")
    assert out["slot"] == 4 and out["changed"] == ["preset", "colour"]
    assert json.loads(route.calls.last.request.content) == {"preset": "My LW-ASA", "colour": "#808080"}
    await srv.set_slot_filament(4, colour="#112233")
    assert json.loads(route.calls.last.request.content) == {"colour": "#112233"}


async def test_set_slot_filament_nothing_to_set_is_local(monkeypatch):
    _env(monkeypatch)
    out = await srv.set_slot_filament(1)
    assert out["error"] == "nothing_to_set"


@respx.mock
async def test_set_slot_filament_unknown_preset_422(monkeypatch):
    _env(monkeypatch)
    respx.put("http://x:13130/api/v1/filaments/1").mock(return_value=httpx.Response(422, json={
        "error": "unknown_preset", "preset": "Nope"}))
    out = await srv.set_slot_filament(1, preset="Nope")
    assert out["error"] == "unknown_preset"


@respx.mock
async def test_set_slot_filament_unknown_slot_404_keeps_message(monkeypatch):
    _env(monkeypatch)
    respx.put("http://x:13130/api/v1/filaments/9").mock(return_value=httpx.Response(404, json={
        "error": "unknown_slot", "count": 4}))
    out = await srv.set_slot_filament(9, preset="X")
    assert out["error"] == "unknown_slot"


@respx.mock
async def test_set_slot_filament_needs_project_build(monkeypatch):
    _env(monkeypatch)
    respx.put("http://x:13130/api/v1/filaments/1").mock(return_value=httpx.Response(404, json={"error": "not_found"}))
    out = await srv.set_slot_filament(1, preset="X")
    assert "fork v2.4.2-mcp.14" in out["error"]


def test_project_tool_annotations():
    tools = srv.mcp._tool_manager._tools
    assert tools["list_filament_slots"].annotations.read_only_hint is True
    assert tools["save_project"].annotations.destructive_hint is False
    assert tools["open_project"].annotations.destructive_hint is True
    assert tools["new_project"].annotations.destructive_hint is True
    assert tools["set_plate"].annotations.destructive_hint is False
    assert tools["set_slot_filament"].annotations.destructive_hint is False
