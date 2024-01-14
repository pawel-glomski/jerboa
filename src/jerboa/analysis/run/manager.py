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


@dataclass
class AlgorithmInstanceDesc:
    algorithm: alg.Algorithm
    analysis_params: alg.AnalysisParams
    interpretation_params: alg.InterpretationParams


@dataclass
class AnalysisRun:
    class State(enum.Enum):
        SUSPENDED = enum.auto()
        RUNNING = enum.auto()
        FINISHED = enum.auto()

    process: mp.Process | None
    ipc: proc.IPC | None

    alg_desc: AlgorithmInstanceDesc
    interpreter: alg.Interpreter

    packets: list[alg.AnalysisPacket] = field(default_factory=list)

    state: State = State.RUNNING


@dataclass
class AnalysisRunView:
    alg_desc: AlgorithmInstanceDesc

    state: AnalysisRun.State

    sections: list[TMSection] = field(default_factory=list)

    @property
    def scope(self) -> float:
        return float("inf") if self.is_done else (self.sections[-1].end if self.sections else 0.0)


class IPCProtocolChild(proc.IPCProtocolChild):
    create_run = proc.IPCMsgDesc("alg_desc")
    resume_run = proc.IPCMsgDesc("run_id")
    reinterpret_run = proc.IPCMsgDesc("run_id", "interpretation_params")
    delete_run = proc.IPCMsgDesc("run_id")
    save = proc.IPCMsgDesc("path")
    load = proc.IPCMsgDesc("path")


class IPCProtocolParent(proc.IPCProtocolParent):
    run_created = proc.IPCMsgDesc("run_id", "algorithm", "state")
    run_reinterpreted = proc.IPCMsgDesc("run_id", "sections")
    run_interpretation_updated = proc.IPCMsgDesc("run_id", "sections")
    run_deleted = proc.IPCMsgDesc("run_id")
    error = proc.IPCMsgDesc("message")


class AnalysisManagementProcess:
    def __init__(self, ipc: proc.IPC):
        self._next_run_id = 0
        self._runs = dict[int, AnalysisRun]()
        self._sync_manager = mp.Manager()

        self._ipc = ipc

        protocol = IPCProtocolChild()
        protocol.create_run = self.__task__create_run
        protocol.resume_run = self.__task__resume_run
        protocol.reinterpret_run = self.__task__reinterpret_run
        protocol.delete_run = self.__task__delete_run
        protocol.save = self.__task__save
        protocol.load = self.__task__load

        self._ipc.configure(protocol)

    def __task__create_run(self, alg_desc: AlgorithmInstanceDesc) -> None:
        assert self._next_run_id not in self._runs

        parent_ipc, child_ipc = proc.IPC.create()
        process = proc.create(
            name=f"Run {alg_desc.algorithm.name}#{self._next_run_id}",
            target=runner.AnalyzerProcess.start,
            ipc=child_ipc,
            analyzer_class=alg_desc.algorithm.analyzer_class,
            environment=alg_desc.algorithm.environment,
            analysis_params=alg_desc.analysis_params,
            last_packet=None,
        )

        protocol = runner.IPCProtocolParent()
        protocol.run_created = self.__task
        protocol.run_reinterpreted = self.__task
        protocol.run_interpretation_updated = self.__task
        protocol.run_deleted = self.__task
        protocol.error = self.__task
        parent_ipc.configure(protocol)

        self._runs[self._next_run_id] = AnalysisRun(
            process=process,
            ipc=parent_ipc,
            alg_desc=alg_desc,
            interpreter=alg_desc.algorithm.interpreter_class(
                environment=alg_desc.algorithm.environment,
                analysis_params=alg_desc.analysis_params,
                interpretation_params=alg_desc.interpretation_params,
            ),
        )

        th.Thread(target=parent_ipc.run, daemon=True).start()

        self._ipc.send(IPCProtocolParent.run_created, run_id=self._next_run_id)

        self._next_run_id += 1

    def __task__resume_run(self, run_id: int) -> None:
        run = self._runs[run_id]
        assert run.state == AnalysisRun.State.SUSPENDED
        assert run.process is None
        assert run.ipc is None

        parent_ipc, child_ipc = proc.IPC.create()
        process = proc.create(
            name=f"Run {run.algorithm.name}#{run_id}",
            target=runner.AnalyzerProcess.start,
            ipc=child_ipc,
            analyzer_class=run.alg_desc.algorithm.analyzer_class,
            environment=run.alg_desc.algorithm.environment,
            analysis_params=run.alg_desc.analysis_params,
            last_packet=None,
        )

        run.process = process
        run.ipc = parent_ipc
        run.state = AnalysisRun.State.RUNNING

    def __task__reinterpret_run(
        self,
        run_id: int,
        interpretation_params: alg.InterpretationParams,
    ) -> None:
        # create a thread for each run that will run the interpreter, change the state of the
        # interpretation thread here, so that there is a single place where the interpretations are
        # sent from
        ...
        # self._ipc.send(IPCProtocol.run_reinterpreted, run_id=run_id, sections=sections)

    def __task__delete_run(self, run_id: int) -> None:
        self._runs[run_id].ipc.kill()
        self._runs.pop(run_id)
        self._ipc.send(IPCProtocolParent.run_deleted, run_id=run_id)

    def __task__save(self, path: str) -> None:
        raise NotImplementedError()

    def __task__load(self, path: str) -> None:
        # updates `self._next_run_id`
        raise NotImplementedError()

    def run(self) -> None:
        self._ipc.run()
        for run in self._runs.values():
            run.ipc.kill()

    @staticmethod
    def start(ipc: proc.IPC) -> None:
        logger.debug("Started Analysis Management Process")
        AnalysisManagementProcess(ipc=ipc).run()


class AnalysisManager:
    def __init__(
        self,
        # show_error_message_signal: Signal,
        # analysis_run_created_signal: Signal,
    ) -> None:
        self._runs = dict[int, AnalysisRunView]()

        self._ipc, child_ipc = proc.IPC.create()

        protocol = IPCProtocolParent()
        protocol.run_created = self.__task__run_created
        protocol.run_reinterpreted = self.__task__run_reinterpreted
        protocol.run_interpretation_updated = self.__task__run_interpretation_updated
        protocol.run_deleted = self.__task__run_interpretation_updated
        protocol.error = self.__task__error

        self._ipc.configure(protocol)
        self._ipc.run_in_background()

        logger.debug("Starting Analysis Management Process")
        self._process = proc.create(
            name="Analysis",
            target=AnalysisManagementProcess.start,
            ipc=child_ipc,
        )
        self._process.start()

    def __del__(self):
        if self._process.is_alive():
            self._process.terminate()

    def __task__run_created(
        self, run_id: int, algorithm: alg.Algorithm, state: AnalysisRun.State
    ) -> None:
        if run_id in self._runs:
            logger.error(
                "Run id collision. the current run will be overwritten and lost.",
                details=(
                    f"current='{algorithm.name}', " f"new='{self._runs[run_id].algorithm.name}'"
                ),
            )
        self._runs[run_id] = AnalysisRunView(algorithm, state)
        self._run_created_signal.emit(run_id=run_id, algorithm=algorithm)

    def __task__run_reinterpreted(self, run_id: int, sections: list[TMSection]) -> None:
        self._runs[run_id].sections = sections
        self._create_timeline()

    def __task__run_interpretation_updated(self, run_id: int, sections: list[TMSection]) -> None:
        self._runs[run_id].sections += sections
        self._update_timeline()

    def __task__error(self, message: str) -> None:
        self._show_error_message_signal.emit(message=message, title=self._error_msg_title)

    def kill(self) -> None:
        self._ipc.kill()

    def wait_dead(self, timeout: float | None, *, terminate_at_timeout: bool = True) -> None:
        self._process.join(timeout=timeout)
        if self._process.is_alive() and terminate_at_timeout:
            logger.warning("Killing Analysis Management Process timed out. Terminating it instead")
            self._process.terminate()

    def run_algorithm(self, alg_desc: AlgorithmInstanceDesc):
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
