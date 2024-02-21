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


from jerboa.log import logger
from jerboa.core import process as proc
from jerboa.core import multithreading as mth
from jerboa.analysis import algorithm as alg


class IPCProtocolParent(proc.IPCProtocolParent):
    analysis_updated = proc.IPCMsgDesc("packet")


class AnalyzerProcess:
    @staticmethod
    def start(
        ipc: proc.IPC,
        analyzer_class: type[alg.Analyzer],
        environment: alg.Environment,
        analysis_params: alg.AnalysisParams,
        last_packet: alg.AnalysisPacket | None,
        resource_manager: alg.ResourceManager,
    ) -> None:
        analyzer_process = AnalyzerProcess(
            ipc=ipc,
            ipc_protocol=proc.IPCProtocolChild(),
            analyzer=analyzer_class(
                environment=environment,
                params=analysis_params,
                resource_manager=resource_manager,
            ),
        )

        analyzer_task = mth.FnTask(lambda executor: analyzer_process.run(executor, last_packet))
        mth.Thread(target=analyzer_task.run_pending, daemon=True).start()

        ipc.run()

        # IPC killed, abort the analyzer's task
        analyzer_task.future.abort()

        # give it some time to finish cleanly
        analyzer_task.future.wait(finishing_aborted=True, timeout=proc.KILL_TIMEOUT)

        # if it's taking a while, just kill the process
        if not analyzer_task.future.stage.is_finished(finishing_aborted=True):
            logger.warning("Analyzer did not finish cleanly in time. Terminating the process.")
            # all subprocesses finish with the `sys.exit` call

    def __init__(
        self,
        ipc: proc.IPC,
        ipc_protocol: proc.IPCProtocolChild,
        analyzer: alg.Analyzer,
    ):
        ipc.configure(protocol=ipc_protocol)

        self._ipc = ipc
        self._analyzer = analyzer

    def run(self, executor: mth.FnTask.Executor, last_packet: alg.AnalysisPacket) -> None:
        try:
            for packet in self._analyzer.analyze(executor=executor, previous_packet=last_packet):
                self._ipc.send(IPCProtocolParent.analysis_updated, packet=packet)
                executor.exit_if_aborted()
            self._ipc.send(IPCProtocolParent.child_finished)
            executor.finish()
        except mth.Task.Abort:
            raise
        except Exception as exception:
            logger.exception("Analyzer crashed with an exception:")
            self._ipc.send(IPCProtocolParent.error, message=f"{exception}")
            raise
