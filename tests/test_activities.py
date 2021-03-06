import json
from collections import namedtuple
from unittest.mock import patch

import attr
import pytest

from pgactivity import activities
from pgactivity.types import (
    IOCounter,
    LoadAverage,
    MemoryInfo,
    RunningProcess,
    SystemProcess,
)


@pytest.fixture
def system_processes(shared_datadir):
    with (shared_datadir / "local-processes-input.json").open() as f:
        input_data = json.load(f)

    fs_blocksize = input_data["fs_blocksize"]

    pg_processes = []
    new_system_procs = {}
    system_procs = {}

    running_process_fields = {a.name for a in attr.fields(RunningProcess)}

    for new_proc in input_data["new_processes"].values():
        new_system_procs[new_proc["pid"]] = SystemProcess.deserialize(
            new_proc["extras"]
        )
        pg_processes.append(
            RunningProcess.deserialize(
                {k: v for k, v in new_proc.items() if k in running_process_fields}
            )
        )

    system_procs = {
        proc["pid"]: SystemProcess.deserialize(proc["extras"])
        for proc in input_data["processes"].values()
    }

    return pg_processes, system_procs, new_system_procs, fs_blocksize


def test_ps_complete(system_processes):
    pg_processes, system_procs, new_system_procs, fs_blocksize = system_processes

    def sys_get_proc(pid):
        return new_system_procs.pop(pid, None)

    n_system_procs = len(system_procs)

    with patch("pgactivity.activities.sys_get_proc", new=sys_get_proc):
        procs, io_read, io_write = activities.ps_complete(
            pg_processes, system_procs, fs_blocksize
        )

    assert not new_system_procs  # all new system processes consumed

    assert io_read == IOCounter.default()
    assert io_write == IOCounter.default()
    assert len(procs) == len(pg_processes)
    assert len(system_procs) == n_system_procs
    assert {p.pid for p in procs} == {
        6221,
        6222,
        6223,
        6224,
        6225,
        6226,
        6227,
        6228,
        6229,
        6230,
        6231,
        6232,
        6233,
        6234,
        6235,
        6237,
        6238,
        6239,
        6240,
    }


def test_ps_complete_empty_procs(system_processes):
    # same as test_ps_complete() but starting with an empty "system_procs" dict
    pg_processes, __, new_system_procs, fs_blocksize = system_processes

    def sys_get_proc(pid):
        return new_system_procs.pop(pid, None)

    system_procs = {}

    with patch("pgactivity.activities.sys_get_proc", new=sys_get_proc):
        procs, io_read, io_write = activities.ps_complete(
            pg_processes, system_procs, fs_blocksize
        )

    assert not new_system_procs  # all new system processes consumed

    assert io_read == IOCounter.default()
    assert io_write == IOCounter.default()
    assert len(procs) == len(pg_processes)
    assert system_procs


def test_mem_swap_load() -> None:
    pmem = namedtuple("pmem", ["percent", "total", "free", "buffers", "cached"])
    vmem = namedtuple("vmem", ["percent", "used", "total"])
    with patch(
        "psutil.virtual_memory", return_value=pmem(12.3, 45, 6, 6, 7)
    ) as virtual_memory, patch(
        "psutil.swap_memory", return_value=vmem(6.7, 8, 90)
    ) as swap_memory, patch(
        "os.getloadavg", return_value=(0.14, 0.27, 0.44)
    ) as getloadavg:
        memory, swap, load = activities.mem_swap_load()
    virtual_memory.assert_called_once_with()
    swap_memory.assert_called_once_with()
    getloadavg.assert_called_once_with()
    assert memory == MemoryInfo(percent=12.3, used=26, total=45)
    assert swap == MemoryInfo(percent=6.7, used=8, total=90)
    assert load == LoadAverage(0.14, 0.27, 0.44)
