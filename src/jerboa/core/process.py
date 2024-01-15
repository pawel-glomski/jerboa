# Jerboa - AI-powered media player
# Copyright (C) 2024 Paweł Głomski

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.


import enum
import typing as t
import multiprocessing as mp
import threading as th
from multiprocessing.connection import Connection
from dataclasses import dataclass, field

from jerboa import utils
from jerboa.log import logger
from jerboa.core.multithreading import TaskQueue, FnTask, Task

KILL_TIMEOUT = 0.25
RECEIVE_POLL_TIMEOUT = 0.05


class Role(enum.Flag):
    PARENT = enum.auto()
    CHILD = enum.auto()


@dataclass(frozen=True, slots=True)
class IPCMsg:
    id: str
    payload: dict[str]


@dataclass(frozen=True)
class IPCMsgDesc:
    id: str = field(default="?", init=False)
    payload: set[str] = field(default_factory=set)

    def __init__(self, *payload: str):
        super().__init__()
        super().__setattr__("payload", set(payload))

    def __set_name__(self, owner, name: str):
        super().__setattr__("id", name)

    def __get__(self, instance, owner) -> t.Callable | None:
        if instance is None:
            return self
        return instance.__dict__.get(self._handler_var_name, None)

    def __set__(self, instance, handler: t.Callable | None):
        utils.assert_callable(handler, expected_args=self.payload)

        instance.__dict__[self._handler_var_name] = handler

    def __delete__(self, instance):
        instance.__dict__.pop(self._handler_var_name, None)

    @property
    def _handler_var_name(self) -> str:
        return f"_{self.id}_handler"

    def create(self, **payload) -> "IPCMsg":
        missing_args = self.payload - payload.keys()
        extra_args = payload.keys() - self.payload
        assert len(missing_args) == 0 and len(extra_args) == 0, f"{missing_args=}, {extra_args=}"

        return IPCMsg(id=self.id, payload=payload)


class IPCProtocol:
    def __init__(self, role: Role):
        super().__setattr__("_role", role)

    def __getitem__(self, msg_id: str) -> t.Callable:
        return getattr(self, msg_id)

    def __setattr__(self, name: str, value) -> None:
        assert hasattr(self.__class__, name), f"Message ({name}) not defined in the protocol."

        super().__setattr__(name, value)

    @property
    def role(self) -> Role:
        return self._role

    def handle(self, msg: IPCMsg) -> Task:
        handler_fn = self[msg.id]
        return FnTask(
            lambda executor: executor.finish_with(handler_fn, **msg.payload),
            id=msg.id,
        )

    def assert_handled(self) -> None:
        msgs_with_missing_handlers = []
        for msg_id in (
            name
            for name, value in self.__class__.__dict__.items()
            if isinstance(value, IPCMsgDesc) and value.receiver_role == self.role
        ):
            if getattr(self, msg_id) is None:
                msgs_with_missing_handlers.append(msg_id)

        assert len(msgs_with_missing_handlers) == 0, (
            f"Protocol has messages with missing handlers: {msgs_with_missing_handlers}",
        )


class IPCProtocolChild(IPCProtocol):
    kill = IPCMsgDesc()

    def __init__(self):
        super().__init__(Role.CHILD)


class IPCProtocolParent(IPCProtocol):
    def __init__(self):
        super().__init__(Role.PARENT)


class IPC:
    def __init__(self, pipe: Connection, role: Role):
        self._pipe = pipe
        self._role = role
        self._is_running = True

        self._tasks: TaskQueue | None = None
        self._protocol: IPCProtocol | None = None

    @property
    def role(self) -> Role:
        return self._role

    def configure(self, protocol: IPCProtocol) -> None:
        assert self._tasks is None, "IPC should be configured exactly once"
        assert self.role == protocol.role

        self._tasks = TaskQueue()

        if isinstance(protocol, IPCProtocolChild) and protocol.kill is None:
            protocol.kill = self.kill
        self._protocol = protocol

    def send(self, msg_desc: IPCMsgDesc, /, **payload):
        msg = msg_desc.create(**payload)
        self._tasks.add_task(FnTask(lambda executor: executor.finish_with(self._pipe.send, msg)))

    def kill(self) -> None:
        def _recursive_kill():
            if self._role & Role.PARENT:
                self.send(IPCProtocol.p2c__kill)
            self._is_running = False

        self._tasks.add_task(FnTask(lambda executor: executor.finish_with(_recursive_kill)))

    def run(self) -> None:
        with logger.catch():
            while self._is_running:
                if self._pipe.poll(RECEIVE_POLL_TIMEOUT):
                    while self._pipe.poll():
                        msg: IPCMsg = self._pipe.recv()
                        handle_task = self._protocol.handle(msg)
                        self._tasks.add_task(handle_task)
                self._tasks.run_all()

    def run_in_background(self):
        th.Thread(target=self.run, daemon=True).start()

    @staticmethod
    def create() -> tuple["IPC", "IPC"]:
        parent, child = mp.Pipe(duplex=True)
        return IPC(parent, role=Role.PARENT), IPC(child, role=Role.CHILD)


def _worker(name: str, target: t.Callable, ipc: IPC, kwargs: dict[str], main_logger):
    logger.initialize(name=name, main_logger=main_logger)
    try:
        target(ipc=ipc, **kwargs)
    except:
        logger.exception("Process has crashed:")
        raise
    finally:
        logger.complete()


def create(name: str, target: t.Callable, ipc: IPC, **kwargs) -> mp.Process:
    return mp.Process(name=name, target=_worker, args=(name, target, ipc, kwargs, logger))
