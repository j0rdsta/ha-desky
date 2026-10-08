# Desky Desk integration tests

The tests use
[pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component),
which runs a real Home Assistant core in-process. BLE traffic is mocked, so no desk is needed.

## Layout

| Path | Covers |
| --- | --- |
| `../conftest.py` | Registers the Home Assistant test plugin (it only works from the root conftest) |
| `__init__.py` | Shared builders, such as `make_service_info()` for Bluetooth discovery |
| `conftest.py` | Shared fixtures (see below) |
| `test_init.py` | Config entry setup and unload |
| `test_config_flow.py` | User and Bluetooth discovery flows, run on Home Assistant's Bluetooth stack with the scanner mocked; `advertise()` injects a desk's advertisement |
| `test_coordinator.py` | `DeskUpdateCoordinator`: refresh, reconnect, disconnect and device info |
| `test_bluetooth.py` | `DeskBLEDevice`: commands, notification parsing, movement and collision detection |
| `test_entities.py` | Snapshot of every entity's registry entry and state |
| `test_<platform>.py` | One file per entity platform: binary sensor, button, cover, light, number, select, sensor, switch |
| `snapshots/` | Snapshot files used by `test_entities.py` |

## Running the tests

Set up a virtual environment as described in [CONTRIBUTING.md](../CONTRIBUTING.md). CI runs the
suite against two Home Assistant versions. To reproduce both locally, keep one environment per
version:

```bash
# Latest stable Home Assistant (Python 3.14)
python3.14 -m venv .venv/latest
.venv/latest/bin/pip install -r requirements_test.txt
.venv/latest/bin/pip install -r <(.venv/latest/bin/python script/ha_test_requirements.py)

# Minimum supported Home Assistant, 2025.10 (Python 3.13)
python3.13 -m venv .venv/min
.venv/min/bin/pip install -r requirements_test_min.txt
.venv/min/bin/pip install -r <(.venv/min/bin/python script/ha_test_requirements.py)
```

Then, with either environment active:

```bash
pytest                                    # the whole suite
pytest tests/test_bluetooth.py            # one file
pytest tests/test_cover.py::test_cover_open_service  # one test
pytest --cov                              # with coverage and the coverage floor
pytest --cov --cov-report=html            # HTML report in htmlcov/index.html
```

## Snapshots

`test_entities.py` sets up a desk with every platform and compares each entity's unique ID,
entity ID, registry metadata and state with `snapshots/test_entities.ambr`. It uses the harness's
`snapshot` fixture ([syrupy](https://github.com/syrupy-project/syrupy) with Home Assistant's
serializer).

A snapshot diff means an entity changed in a way users would see. Unique IDs and entity IDs must
never change for existing users, so treat a diff in either as a bug unless the change ships with
a migration. When the change is intended, regenerate the snapshot and commit the updated file:

```bash
pytest tests/test_entities.py --snapshot-update
```

Check that the snapshot still passes on both Home Assistant versions. Attributes that Home Assistant
itself added within the supported range are left out of the snapshot (see
`VERSION_DEPENDENT_ATTRIBUTES`).

## Warnings are errors

`pyproject.toml` sets `filterwarnings = ["error"]`, so any warning fails the test that raised it.
The only ignores are for warnings raised inside dependencies, each scoped to its message and
module with a comment giving the cause. Fix a new warning in the test or the integration rather
than adding an ignore. A coroutine that is never awaited usually means a patched
`asyncio.create_task`: close the coroutine in the patch, as `tests/test_coordinator.py` does.

## Coverage

`pytest --cov` measures statement and branch coverage of `custom_components/desky_desk` and fails
below the floor set by `fail_under` in `pyproject.toml`. Raise the floor when coverage improves;
never lower it to get a change through.

## Fixtures

In `conftest.py`:

- `mock_config_entry`: a `MockConfigEntry` for a desk at `AA:BB:CC:DD:EE:FF`
- `mock_desk`: the desk's BLE device, autospecced from `DeskBLEDevice` and connected; assert
  commands on it, such as `mock_desk.move_to_preset.assert_awaited_once_with(2)`
- `init_integration`: sets the integration up through Home Assistant with `mock_desk` and
  returns the entry; the coordinator is `entry.runtime_data`
- `mock_coordinator_data`: the `DeskData` snapshot matching `mock_desk`
- `mock_ble_device`, `mock_service_info`: discovery inputs
- `mock_bleak_client`: a Bleak client mock specced to the real `BleakClient`
- `mock_bleak_client_with_device_info`: the same client with the Device Information Service

Custom integrations are enabled for every test automatically.

Helpers in `__init__.py` change the desk's state:

- `set_desk_state(hass, entry, **changes)`: replaces fields of the coordinator data
- `notify_desk(desk, **changes)`: changes `mock_desk` and sends a notification, as the desk does
- `disconnect_desk(desk)`: disconnects `mock_desk`
- `desk_data(**changes)`: builds a `DeskData` for a connected desk

## Writing tests

- Mock at the boundary (Bleak, `establish_connection`, Home Assistant's Bluetooth helpers), not the
  integration's own classes.
- Drive platforms through `hass.services.async_call` and assert on `hass.states`, as users and
  automations do.
- Cover failure paths as well as the happy path.
