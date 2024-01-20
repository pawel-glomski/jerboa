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
import threading as th
import multiprocessing as mp
from dataclasses import dataclass, field


from jerboa.log import logger
from jerboa.core.signal import Signal
from jerboa.core.timeline import TMSection

from jerboa.analysis import algorithm as alg
from jerboa.core import process as proc
from . import runner


RUN_FINISH_TIMEOUT = 5


@dataclass
class AnalysisRun:
    class State(enum.Enum):
        SUSPENDED = enum.auto()
        RUNNING = enum.auto()
        FINISHED = enum.auto()

    process: mp.Process | None
    ipc: proc.IPC | None

    alg_desc: alg.AlgorithmInstanceDesc
    interpreter: alg.Interpreter

    packets: list[alg.AnalysisPacket] = field(default_factory=list)

    state: State = State.RUNNING


@dataclass
class AnalysisRunView:
    alg_desc: alg.AlgorithmInstanceDesc

    state: AnalysisRun.State

    sections: list[TMSection] = field(default_factory=list)

    @property
    def scope(self) -> float:
        return (
            float("inf")
            if self.state == AnalysisRun.State.FINISHED
            else (self.sections[-1].end if self.sections else 0.0)
        )


class IPCProtocolChild(proc.IPCProtocolChild):
    create_run = proc.IPCMsgDesc("alg_desc", response_timeout=0.5)
    resume_run = proc.IPCMsgDesc("run_id")
    reinterpret_run = proc.IPCMsgDesc("run_id", "interpretation_params", response_timeout=10)
    delete_run = proc.IPCMsgDesc("run_id")
    save = proc.IPCMsgDesc("path")
    load = proc.IPCMsgDesc("path")


class IPCProtocolParent(proc.IPCProtocolParent):
    run_created = proc.IPCMsgDesc("run_id", "run_view")
    run_deleted = proc.IPCMsgDesc("run_id")
    run_reinterpreted = proc.IPCMsgDesc("run_id", "sections")
    run_interpretation_updated = proc.IPCMsgDesc("run_id", "sections")
    run_finished = proc.IPCMsgDesc("run_id")
    run_suspended = proc.IPCMsgDesc("run_id")


class AnalysisManagementProcess:
    @staticmethod
    def start(ipc: proc.IPC) -> None:
        AnalysisManagementProcess(ipc=ipc).run()

    def __init__(self, ipc: proc.IPC):
        self._next_run_id = 0
        self._runs = dict[int, AnalysisRun]()

        self._sync_manager = mp.Manager()  # this can take a while in debug mode (~2 seconds)

        self._ipc = ipc

        protocol = IPCProtocolChild()
        protocol.create_run = self.__ipc__create_run
        protocol.resume_run = self.__ipc__resume_run
        protocol.reinterpret_run = self.__ipc__reinterpret_run
        protocol.delete_run = self.__ipc__delete_run
        protocol.save = self.__ipc__save
        protocol.load = self.__ipc__load

        self._ipc.configure(protocol)

    def __ipc__create_run(self, alg_desc: alg.AlgorithmInstanceDesc) -> None:
        assert self._next_run_id not in self._runs

        run_id = self._next_run_id
        self._next_run_id += 1

        parent_ipc, child_ipc = proc.IPC.create()

        process = proc.create(
            f"Run #{run_id} ({alg_desc.algorithm.name})",
            runner.AnalyzerProcess.start,
            child_ipc,
            analyzer_class=alg_desc.algorithm.analyzer_class,
            environment=alg_desc.algorithm.environment,
            analysis_params=alg_desc.analysis_params,
            last_packet=None,
        )
        process.start()

        def run_updated(packet: alg.AnalysisPacket) -> None:
            self._runs[run_id].packets.append(packet)
            self._runs[run_id].new_packets.notify_all()

        def run_finished() -> None:
            self._runs[run_id].state = AnalysisRun.State.FINISHED
            self._ipc.send(IPCProtocolParent.run_finished, run_id=run_id)

        def run_error(message: str) -> None:
            self._ipc.send(IPCProtocolParent.error, message=message)

        protocol = runner.IPCProtocolParent()
        protocol.analysis_updated = run_updated
        protocol.child_finished = run_finished
        protocol.error = run_error
        parent_ipc.configure(protocol)

        self._runs[run_id] = AnalysisRun(
            process=process,
            ipc=parent_ipc,
            alg_desc=alg_desc,
            interpreter=alg_desc.algorithm.interpreter_class(
                environment=alg_desc.algorithm.environment,
                analysis_params=alg_desc.analysis_params,
                interpretation_params=alg_desc.interpretation_params,
            ),
        )

        self._ipc.send(
            IPCProtocolParent.run_created,
            run_id=run_id,
            run_view=AnalysisRunView(
                alg_desc=alg_desc,
                state=self._runs[run_id].state,
                sections=[],
            ),
        )

        th.Thread(
            name=f"IPC-{parent_ipc.role.name} thread: {process.name}",
            target=self._run_ipc,
            args=[run_id],
            daemon=True,
        ).start()

    def _run_ipc(self, run_id: int) -> None:
        run = self._runs[run_id]
        try:
            run.ipc.run()
            run.process.join(RUN_FINISH_TIMEOUT)  # for some reason this takes ~1s in debug
            if run.process.is_alive():
                logger.warning(
                    f"Finishing analysis run #{run_id} '{run.process.name}' has timed out. "
                    "Terminating it instead"
                )
                run.process.terminate()
        finally:
            if run.state == AnalysisRun.State.RUNNING:
                run.state = AnalysisRun.State.SUSPENDED
                self._ipc.send(IPCProtocolParent.run_suspended, run_id=run_id)

    def __ipc__resume_run(self, run_id: int) -> None:
        run = self._runs[run_id]
        if run.process is not None and run.process.is_alive():
            run.process.terminate()
        assert run.state == AnalysisRun.State.SUSPENDED
        assert run.process is None
        assert run.ipc is None

        parent_ipc, child_ipc = proc.IPC.create()
        process = proc.create(
            f"Run {run.algorithm.name}#{run_id}",
            runner.AnalyzerProcess.start,
            child_ipc,
            analyzer_class=run.alg_desc.algorithm.analyzer_class,
            environment=run.alg_desc.algorithm.environment,
            analysis_params=run.alg_desc.analysis_params,
            last_packet=...,  # TODO
        )
        process.start()

        run.process = process
        run.ipc = parent_ipc
        run.state = AnalysisRun.State.RUNNING

    def __ipc__reinterpret_run(
        self,
        run_id: int,
        interpretation_params: alg.InterpretationParams,
    ) -> None:
        # create a thread for each run that will run the interpreter, change the state of the
        # interpretation thread here, so that there is a single place where the interpretations are
        # sent from
        ...
        # self._ipc.send(IPCProtocol.run_reinterpreted, run_id=run_id, sections=sections)

    def __ipc__delete_run(self, run_id: int) -> None:
        self._runs[run_id].ipc.kill()
        self._runs.pop(run_id)
        self._ipc.send(IPCProtocolParent.run_deleted, run_id=run_id)

    def __ipc__save(self, path: str) -> None:
        raise NotImplementedError()

    def __ipc__load(self, path: str) -> None:
        # updates `self._next_run_id`
        raise NotImplementedError()

    def run(self) -> None:
        try:
            self._ipc.run()
        finally:
            for run in self._runs.values():
                run.ipc.kill()


class AnalysisManager:
    def __init__(
        self,
        error_message_title: str,
        show_error_message_signal: Signal,
        run_created_signal: Signal,
    ) -> None:
        self._error_message_title = error_message_title
        self._show_error_message_signal = show_error_message_signal

        self._run_created_signal = run_created_signal

        self._runs = dict[int, AnalysisRunView]()

        self._ipc, child_ipc = proc.IPC.create()

        protocol = IPCProtocolParent()
        protocol.run_created = self.__ipc__run_created
        protocol.run_deleted = self.__ipc__run_deleted
        protocol.run_reinterpreted = self.__ipc__run_reinterpreted
        protocol.run_interpretation_updated = self.__ipc__run_interpretation_updated
        protocol.run_finished = self.__ipc__run_finished
        protocol.run_suspended = self.__ipc__run_suspended
        protocol.error = self.__ipc__error

        self._ipc.configure(protocol)
        th.Thread(
            target=self._ipc_thread,
            daemon=True,
            name=f"IPC-{self._ipc.role.name} thread: Analysis Management Process",
        ).start()

        self._process = proc.create("Analysis", AnalysisManagementProcess.start, child_ipc)
        self._process.start()

    def __del__(self):
        if self._process.is_alive():
            logger.error("Forced termination")
            self._process.terminate()

    def _ipc_thread(self) -> None:
        try:
            self._ipc.run()
        except Exception as exception:
            # TODO?: Add a crash signal that will display a message and close the app
            self.__ipc__error(message=str(exception))

    def __ipc__run_created(self, run_id: int, run_view: AnalysisRunView) -> None:
        if run_id in self._runs:
            logger.error(
                "Run id collision. Please report this error.",
                details=(
                    f"current='{run_view.alg_desc.algorithm.name}'",
                    f"new='{self._runs[run_id].algorithm.name}'",
                ),
            )

        self._runs[run_id] = run_view
        self._run_created_signal.emit(run_id=run_id, algorithm=run_view.alg_desc.algorithm)

    def __ipc__run_deleted(self, run_id: int) -> None:
        self._run_deleted_singal.emit(run_id=run_id)
        self._runs.pop(run_id)

    def __ipc__run_reinterpreted(self, run_id: int, sections: list[TMSection]) -> None:
        self._runs[run_id].sections = sections
        self._create_timeline()

    def __ipc__run_interpretation_updated(self, run_id: int, sections: list[TMSection]) -> None:
        self._runs[run_id].sections += sections
        self._update_timeline()

    def __ipc__run_finished(self, run_id: int) -> None:
        self._runs[run_id].state = AnalysisRun.State.FINISHED
        self._update_timeline()

    def __ipc__run_suspended(self, run_id: int) -> None:
        self._runs[run_id].state = AnalysisRun.State.SUSPENDED
        self._update_timeline()

    def __ipc__error(self, message: str) -> None:
        self._show_error_message_signal.emit(message=message, title=self._error_message_title)

    def _update_timeline(self) -> None:
        ...

    def kill(self) -> None:
        self._ipc.kill()

    def wait_dead(self, timeout: float | None, *, terminate_at_timeout: bool = True) -> None:
        self._process.join(timeout=timeout)
        if self._process.is_alive() and terminate_at_timeout:
            logger.warning("Killing Analysis Management Process timed out. Terminating it instead")
            self._process.terminate()

    def run_algorithm(self, alg_desc: alg.AlgorithmInstanceDesc):
        self._ipc.send(IPCProtocolChild.create_run, alg_desc=alg_desc)

    def reinterpret_run(self, run_id: int, interpretation_params: alg.InterpretationParams) -> None:
        self._ipc.send(
            IPCProtocolChild.reinterpret_run,
            run_id=run_id,
            interpretation_params=interpretation_params,
        )

    def delete_run(self, run_id: int) -> None:
        self._ipc.send(IPCProtocolChild.delete_run, run_id=run_id)

    def save(self, path: str) -> None:
        raise NotImplementedError()

    def load(self, path: str) -> None:
        raise NotImplementedError()
