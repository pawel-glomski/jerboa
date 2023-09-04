import io

from abc import ABC, abstractmethod
from pathlib import Path

from jerboa.timeline import FragmentedTimeline

ARG_PREPARE_ANALYSIS_METHOD_FN = "prepare_fn"
# ANALYSIS_RESULTS_DIR = sl_file.create_cache_dir_rel('analysis_results')
ANALYSIS_RESULTS_EXT = "ares"


class Analysis(ABC):
    def __init__(self, recording_path: str, transcript_path: str) -> None:
        self.recording_path = Path(recording_path)
        self.transcript_path = Path(transcript_path)
        if not self.recording_path.exists():
            raise FileNotFoundError()

        self.settings = None  # changable settings

        self.subs = []  # timeline update subscribers

        raise NotImplementedError()

    def update_subscribers(self) -> None:
        timeline = self.get_timeline()
        for sub in self.subs:
            sub(timeline)

    @abstractmethod
    def change_settings(self, settings: object) -> None:
        raise NotImplementedError()

    def save_to_file(self, analysis_path: Path = None):
        analysis_path = analysis_path or Analysis.get_analysis_file_path(analysis_path)
        with Analysis.open_analysis_file(analysis_path, "w") as analysis_file:
            self.write_to(analysis_file)

    @staticmethod
    def get_analysis_file_path(recording_path: Path) -> Path:
        recording_path = Path(recording_path)
        return recording_path.parent / f"{recording_path.stem}.{ANALYSIS_RESULTS_EXT}"

    @staticmethod
    def open_analysis_file(analysis_path: Path, mode: str = "r"):
        analysis_path = Path(analysis_path)
        if not analysis_path.is_file():
            raise ValueError()
        return open(analysis_path, mode, encoding="UTF-8")

    @abstractmethod
    def write_to(self, output: io.TextIOBase):
        raise NotImplementedError()

    @staticmethod
    def load_from_file(analysis_path: Path) -> "Analysis":
        analysis_path = Path(analysis_path)
        with Analysis.open_analysis_file(analysis_path, "r") as analysis_file:
            raise NotImplementedError()

    @abstractmethod
    def get_timeline(self) -> FragmentedTimeline:
        raise NotImplementedError()


class AnalysisMethod(ABC):
    def __init__(self, name: str):
        self.name = name

    def analyze(self, recording_path: str, subtitles_path: str = None) -> Analysis:
        raise NotImplementedError()
