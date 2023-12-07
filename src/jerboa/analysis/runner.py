from typing import Any, Callable
from abc import ABC, abstractmethod

import threading as th
import multiprocessing as mp
from multiprocessing.connection import Connection
from pathlib import Path
from functools import partial

from jerboa.core import timeline
from .algorithm import Algorithm
from .parameter import Parameter


class MostRecentState:
    class EOF:
        ...

    def __init__(self, receiver: Connection) -> None:
        assert receiver.readable
        self._receiver = receiver

        self._state = None
        self._is_done = False

        self._mutex = th.Lock()
        self._has_state_or_is_done = th.Condition(self._mutex)
        self._receive_thread = th.Thread(target=self._receive)
        self._receive_thread.start()

    @property
    def is_done(self) -> bool:
        return self._is_done

    def __del__(self):
        if hasattr(self, "_receive_thread") and self._receive_thread.is_alive():
            self._is_done = True
            self._receive_thread.join()

    def _receive(self):
        while not self.is_done:
            try:
                new_state = self._receiver.recv()
                if isinstance(new_state, MostRecentState.EOF):
                    break
            except EOFError:
                break

            with self._mutex:
                self._state = new_state
                self._has_state_or_is_done.notify()

        with self._mutex:
            self._is_done = True
            self._has_state_or_is_done.notify_all()

    def pop_state(self):
        with self._mutex:
            self._has_state_or_is_done.wait_for(lambda: self._state is not None or self.is_done)
            state = self._state
            self._state = None
            return state


class Action:
    @staticmethod
    def command_change_timeline_parameters(
        parameters: list[Parameter],
    ) -> Callable[["AnalysisRun"], Callable[["AnalysisRunProxy"], Any]]:
        def command(analysis_run: "AnalysisRun"):
            new_timeline = analysis_run.change_timeline_parameters(parameters)

            # response:
            return partial(
                AnalysisRunProxy.response_set_timeline_after_parameters_change,
                new_timeline=new_timeline,
            )

        return command

    @staticmethod
    def command_save_to_file(
        path: Path,
    ) -> Callable[["AnalysisRun"], Callable[["AnalysisRunProxy"], Any]]:
        def command(
            analysis_run: "AnalysisRun",
        ) -> Callable[["AnalysisRunProxy"], None]:
            success, message = analysis_run.save_to_file(path)

            if success:
                return partial(AnalysisRunProxy.saving_succeded, message=message)
            return partial(AnalysisRunProxy.saving_failed, message=message)

        return command

    @staticmethod
    def command_stop() -> Callable[["AnalysisRun"], None]:
        return AnalysisRun.signal_stop

    @staticmethod
    def response_clean_stop() -> Callable[["AnalysisRunProxy"], None]:
        return AnalysisRunProxy.clean_stop

    @staticmethod
    def response_messy_stop(messages: list[str]) -> Callable[["AnalysisRunProxy"], Any]:
        return partial(AnalysisRunProxy.messy_stop, messages=messages)

    @staticmethod
    def response_analysis_update(
        sections: list[timeline.TMSection],
    ) -> Callable[["AnalysisRunProxy"], Any]:
        return partial(AnalysisRunProxy.analysis_update, sections=sections)

    @staticmethod
    def response_analysis_finished() -> Callable[["AnalysisRunProxy"], Any]:
        return AnalysisRunProxy.analysis_finished

    @staticmethod
    def response_analysis_exception(
        exception: Exception,
    ) -> Callable[["AnalysisRunProxy"], Any]:
        return partial(AnalysisRunProxy.analysis_exception, exception=exception)

    @staticmethod
    def response_command_exception(
        command: Callable[["AnalysisRun"], Any], exception: Exception
    ) -> Callable[["AnalysisRunProxy"], Any]:
        return partial(AnalysisRunProxy.command_exception, command=command, exception=exception)


class AnalysisRun:
    RECEIVE_POLL_TIMEOUT = 0.1  # TODO: figure out good timeout
    STOP_TIMEOUT = 5.0

    def __init__(
        self,
        algorithm: Algorithm,
        recording_path: Path,
        transcript_path: Path | None,
        pipe: Connection,
    ):
        self._algorithm = algorithm
        self._pipe = pipe
        self._stop = False

        self._responses = list[Callable[["AnalysisRun"], None]]()
        self._responses_mutex = th.Lock()

        self._commands = list[Callable[["AnalysisRun"], None]]()
        self._commands_mutex = th.Lock()
        self._commands_not_empty_or_stopping = th.Condition(self._commands_mutex)
        self._commands_executing_thread = th.Thread(target=self._commands_executing_task)

        self._analysis_thread = th.Thread(
            target=self._analysis_task,
            kwargs={
                "recording_path": recording_path,
                "transcript_path": transcript_path,
            },
        )

        self._analysis_thread.start()
        self._commands_executing_thread.start()

    def _analysis_task(self, recording_path: Path, transcript_path: Path) -> None:
        try:
            for new_sections in self._algorithm.analyze(recording_path, transcript_path):
                self.add_response(Action.response_analysis_update(new_sections))
        except Exception as e:
            self.add_response(Action.response_analysis_exception(e))
        else:
            self.add_response(Action.response_analysis_finished())

    def _commands_executing_task(self) -> None:
        while not self._stop:
            with self._commands_mutex:
                self._commands_not_empty_or_stopping.wait_for(lambda: self._commands or self._stop)
                commands, self._commands = self._commands, []

            for command in commands:
                self.execute_command_and_send_response(command)

    def execute_command_and_send_response(
        self, command: Callable[["AnalysisRun"], Callable[["AnalysisRun"], Any] | None]
    ) -> None:
        try:
            response = command(self)
        except Exception as e:
            self.add_response(Action.response_command_exception(command, e))
        else:
            if response:
                self.add_response(response)

    def add_response(self, response: Callable[["AnalysisRun"], Any]) -> None:
        with self._responses_mutex:
            self._responses.append(response)

    def receive_commands_send_responses(self) -> None:
        while not self._stop:
            self._receive_commands()
            self._send_responses()

        error_messages = self._await_stop()
        if error_messages:
            self.add_response(Action.response_messy_stop(error_messages))
        else:
            self.add_response(Action.response_clean_stop())
        self._send_responses()

    def _receive_commands(self) -> None:
        if self._pipe.poll(AnalysisRun.RECEIVE_POLL_TIMEOUT):
            with self._commands_mutex:
                while self._pipe.poll():
                    command: Callable[
                        ["AnalysisRun"], Callable[["AnalysisRun"], Any]
                    ] = self._pipe.recv()
                    self._commands.append(command)
                    self._commands_not_empty_or_stopping.notify()

    def _send_responses(self) -> None:
        responses = []
        with self._responses_mutex:
            if self._responses:
                responses, self._responses = self._responses, responses

        for response in responses:
            self._pipe.send(response)

    def _await_stop(self) -> list[str]:
        self._analysis_thread.join(timeout=AnalysisRun.STOP_TIMEOUT)
        self._commands_executing_thread.join(timeout=AnalysisRun.STOP_TIMEOUT)

        error_messages = []
        if self._analysis_thread.is_alive():
            error_messages.append("Analysis thread does not respond")
        if self._commands_executing_thread.is_alive():
            error_messages.append("Commands executing thread does not respond")
        return error_messages

    def signal_stop(self) -> None:
        self._stop = True
        self._commands_not_empty_or_stopping.notify()

    def change_timeline_parameters(
        self, parameters: list[Parameter]
    ) -> timeline.FragmentedTimeline:
        self._algorithm.change_timeline_parameters(parameters)
        return self._algorithm.generate_new_timeline()

    def save_to_file(self, path: Path) -> tuple[bool, str]:
        return self._algorithm.save_to_file(path)

    @staticmethod
    def run(
        algorithm: Algorithm,
        recording_path: Path,
        transcript_path: Path | None,
        pipe: Connection,
    ) -> None:
        analysis_run = AnalysisRun(
            algorithm=algorithm,
            recording_path=recording_path,
            transcript_path=transcript_path,
            pipe=pipe,
        )
        analysis_run.receive_commands_send_responses()


class AnalysisRunObserver(ABC):
    @abstractmethod
    def saving_failed(self, error_msg: str):
        raise NotImplementedError()

    @abstractmethod
    def saving_succeded(self, error_msg: str):
        raise NotImplementedError()


class AnalysisRunProxy:
    def __init__(self, algorithm: Algorithm, observer: AnalysisRunObserver) -> None:
        self._algorithm = algorithm
        self._observer = observer
        self._stopped = False
        self._pipe: Connection = None

    def start(self, recording_path: Path, transcript_path: Path) -> None:
        assert self._pipe is None

        self._pipe, run_pipe = mp.Pipe()

        process = mp.Process(
            target=AnalysisRun.run,
            args=[self._algorithm, recording_path, transcript_path, run_pipe],
        )
        process.start()

    def stop(self) -> None:
        if self._pipe is not None and not self._pipe.closed:
            self._pipe.send(Action.command_stop())
