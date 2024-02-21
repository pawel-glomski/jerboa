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


import sys
import enum
import time
import typing as T
import multiprocessing as mp
from multiprocessing.connection import Connection
from dataclasses import dataclass, field

from jerboa import utils
from jerboa.log import logger
from jerboa.core.multithreading import TaskQueue, FnTask, Task


CHILD_CREATE_TIMEOUT = 10  # in seconds
KILL_TIMEOUT = 0.25  # inf seconds
RECEIVE_POLL_TIMEOUT = 0.05  # in seconds
RECEIVE_POLL_MSG_NUM_MAX = 16  # max number of messages that will be pulled from the pipe at once


class Role(enum.Enum):
    PARENT = enum.auto()
    CHILD = enum.auto()


@dataclass(frozen=True, slots=True)
class IPCMsg:
    id: str
    payload: dict[str]


@dataclass(frozen=True, init=False)
class IPCMsgDesc:
    id: str = field(default="?")
    payload: set[str] = field(default_factory=set)
    response_timeout: float | None

    def __init__(self, *payload: str, response_timeout: float | None = None):
        super().__init__()
        super().__setattr__("payload", set(payload))
        super().__setattr__("response_timeout", response_timeout)

    def __set_name__(self, owner, name: str):
        super().__setattr__("id", name)

    def __get__(self, instance, owner) -> T.Callable | None:
        if instance is None:
            return self
        return instance.__dict__.get(self._handler_var_name, None)

    def __set__(self, instance, handler: T.Callable | None):
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

    def __getitem__(self, msg_id: str) -> T.Callable:
        return getattr(self, msg_id)

    def __setattr__(self, name: str, value) -> None:
        assert hasattr(self.__class__, name), f"Message '{name}' not defined in the protocol."

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
            name for name, value in self.__class__.__dict__.items() if isinstance(value, IPCMsgDesc)
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
    child_created = IPCMsgDesc()
    child_finished = IPCMsgDesc()
    error = IPCMsgDesc("message")

    def __init__(self):
        super().__init__(Role.PARENT)


class IPC:
    def __init__(self, pipe: Connection, role: Role):
        self._pipe = pipe
        self._role = role
        self._is_running = True

        self._protocol: IPCProtocol | None = None

        self._tasks: TaskQueue | None = None

        self._response_timeout_end: float = float("inf")

    @property
    def role(self) -> Role:
        return self._role

    def configure(self, protocol: IPCProtocol) -> None:
        assert self._tasks is None, "IPC should be configured exactly once"
        assert self.role == protocol.role

        self._tasks = TaskQueue()

        if self.role == Role.CHILD:
            self._configure_as_child(protocol)
        if self.role == Role.PARENT:
            self._configure_as_parent(protocol)
        protocol.assert_handled()

        self._protocol = protocol

    def _configure_as_child(self, protocol: IPCProtocolChild) -> None:
        protocol.kill = IPC._stack_handlers(protocol.kill, self.__run__kill)

    def _configure_as_parent(self, protocol: IPCProtocolParent) -> None:
        protocol.child_created = IPC._stack_handlers(
            protocol.child_created, lambda: logger.debug("The child process has checked in")
        )
        protocol.child_finished = IPC._stack_handlers(protocol.child_finished, self.__run__kill)

    @staticmethod
    def _stack_handlers(*handlers: T.Callable) -> T.Callable:
        def _wrapped_handler(**kwargs):
            for handler in handlers:
                if handler is not None:
                    handler(**kwargs)

        return _wrapped_handler

    def send(self, msg_desc: IPCMsgDesc, /, **payload):
        self._tasks.add_task(
            FnTask(lambda executor: executor.finish_with(self.__run__send, msg_desc, **payload))
        )

    def __run__send(self, msg_desc: IPCMsgDesc, /, **payload) -> None:
        logger.debug(f"Sending a message: '{msg_desc.id}'")

        self._pipe.send(msg_desc.create(**payload))
        if msg_desc.response_timeout is not None:
            self.__run__update_response_timeout(msg_desc.response_timeout)

    def __run__update_response_timeout(self, response_timeout: float) -> None:
        response_timeout_end = time.time() + response_timeout
        if response_timeout_end < self._response_timeout_end:
            self._response_timeout_end = response_timeout_end

    def kill(self) -> None:
        self._tasks.add_task(FnTask(lambda executor: executor.finish_with(self.__run__kill)))

    def __run__kill(self) -> None:
        try:
            if self._role == Role.PARENT and not self._pipe.closed:
                self.send(IPCProtocolChild.kill)
        finally:
            self._is_running = False

    def run(self) -> None:
        try:
            if self.role == Role.CHILD:
                self.__run__send(IPCProtocolParent.child_created)
            if self.role == Role.PARENT:
                if msg_task := self._receive_msg(timeout=CHILD_CREATE_TIMEOUT):
                    msg_task.run_pending()
                else:
                    raise TimeoutError("Child process creation timed out")

            while self._is_running:
                if self._pipe.poll(RECEIVE_POLL_TIMEOUT):
                    while len(self._tasks) < RECEIVE_POLL_MSG_NUM_MAX:
                        if msg_task := self._receive_msg(timeout=0):
                            self._response_timeout_end = float("inf")
                            self._tasks.add_task(msg_task)
                        else:
                            break

                if self._response_timeout_end <= time.time():
                    raise TimeoutError("Unresponsive IPC")

                self._tasks.run_all()

            logger.debug("IPC ends as requested")
        except Exception as exception:
            logger.exception("IPC crashed with the following exception:")

            self.__run__kill()
            if self.role == Role.CHILD and not self._pipe.closed:
                self.__run__send(IPCProtocolParent.error, message=str(exception))
            raise

    def _receive_msg(self, *, timeout: float) -> Task | None:
        if self._pipe.poll(timeout):
            msg: IPCMsg = self._pipe.recv()
            logger.debug(f"Received a message: '{msg.id}'")

            return self._protocol.handle(msg)
        return None

    @staticmethod
    def create() -> tuple["IPC", "IPC"]:
        parent, child = mp.Pipe(duplex=True)
        return IPC(parent, role=Role.PARENT), IPC(child, role=Role.CHILD)


def _worker(name: str, target: T.Callable, ipc: IPC, kwargs: dict[str], main_logger):
    logger.initialize(name=name, main_logger=main_logger)
    try:
        logger.debug("The subprocess has started")
        target(ipc=ipc, **kwargs)
        logger.debug("The subprocess has finished")
    except:
        logger.exception("Process has crashed:")
        raise
    finally:
        logger.complete()
    sys.exit()


# TODO
# import concurrent.futures
# executor = concurrent.futures.ProcessPoolExecutor()
def create(name: str, target: T.Callable, ipc: IPC, /, **kwargs) -> mp.Process:
    logger.debug(f"Creating a subprocess: `{name}`")
    return mp.Process(name=name, target=_worker, args=(name, target, ipc, kwargs, logger))
