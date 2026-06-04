from __future__ import annotations

import shutil
import tarfile
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ....speech_assets import (
    acquire_download_lock,
    download_file,
    file_name_from_url,
    replace_directory,
    safe_extract_tar,
    write_download_metadata,
)

DEFAULT_KOKORO_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"
    "kokoro-multi-lang-v1_1.tar.bz2"
)


@dataclass(slots=True, frozen=True)
class KokoroModelPaths:
    root_dir: Path
    model_file: Path
    voices_file: Path
    tokens_file: Path
    data_dir: Path
    dict_dir: Path


@dataclass(slots=True, frozen=True)
class KokoroDownloadSettings:
    model_url: str
    timeout_seconds: float
    allow_private_download: bool


class KokoroPreparationCancelled(RuntimeError):
    pass


class KokoroModelManager:
    def __init__(
        self,
        workspace: Path,
        *,
        model_root_dir: Path | None = None,
        model_url: str = DEFAULT_KOKORO_URL,
        timeout_seconds: float = 600.0,
        allow_private_download: bool = False,
    ) -> None:
        root_dir = model_root_dir or (
            workspace / ".echobot" / "models" / "sherpa-onnx" / "kokoro-multi-lang-v1_1"
        )
        self._paths = KokoroModelPaths(
            root_dir=root_dir,
            model_file=root_dir / "model.onnx",
            voices_file=root_dir / "voices.bin",
            tokens_file=root_dir / "tokens.txt",
            data_dir=root_dir / "espeak-ng-data",
            dict_dir=root_dir / "dict",
        )
        self._settings = KokoroDownloadSettings(
            model_url=model_url,
            timeout_seconds=timeout_seconds,
            allow_private_download=allow_private_download,
        )

    @property
    def paths(self) -> KokoroModelPaths:
        return self._paths

    @property
    def settings(self) -> KokoroDownloadSettings:
        return self._settings

    def lexicon_files(self) -> tuple[Path, ...]:
        return tuple(sorted(self._paths.root_dir.glob("lexicon*.txt")))

    def models_ready(self) -> bool:
        return not self.missing_files()

    def missing_files(self) -> list[Path]:
        required_paths: list[Path] = [
            self._paths.model_file,
            self._paths.voices_file,
            self._paths.tokens_file,
        ]
        missing_paths = [path for path in required_paths if not path.is_file()]
        if not self._paths.data_dir.is_dir():
            missing_paths.append(self._paths.data_dir)
        return missing_paths

    def prepare_required_files(
        self,
        *,
        stop_event: threading.Event | None = None,
    ) -> KokoroModelPaths:
        self._ensure_not_cancelled(stop_event)
        if self.models_ready():
            return self._paths

        self._paths.root_dir.parent.mkdir(parents=True, exist_ok=True)
        with self._acquire_download_lock(stop_event):
            self._ensure_not_cancelled(stop_event)
            if self.models_ready():
                return self._paths
            self._install_model(stop_event)
        return self._paths

    def _install_model(
        self,
        stop_event: threading.Event | None,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="echobot_kokoro_") as temp_dir:
            temp_root = Path(temp_dir)
            archive_name = file_name_from_url(
                self._settings.model_url,
                allow_private=self._settings.allow_private_download,
            )
            archive_path = temp_root / archive_name
            extract_dir = temp_root / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)

            download_file(
                self._settings.model_url,
                archive_path,
                timeout_seconds=self._settings.timeout_seconds,
                allow_private=self._settings.allow_private_download,
                stop_event=stop_event,
                cancelled_error_factory=self._cancelled_error,
                progress_label="Kokoro TTS model",
            )
            self._ensure_not_cancelled(stop_event)
            with tarfile.open(archive_path, "r:*") as archive:
                safe_extract_tar(archive, extract_dir)

            self._ensure_not_cancelled(stop_event)
            source_dir = self._find_directory_with_model_files(extract_dir)
            source_model = self._find_model_file(source_dir)
            source_data_dir = self._find_optional_directory(source_dir, "espeak-ng-data")
            source_dict_dir = self._find_optional_directory(source_dir, "dict")
            source_lexicons = sorted(source_dir.rglob("lexicon*.txt"))

            temp_install_dir = self._paths.root_dir.with_name(f"{self._paths.root_dir.name}.tmp")
            if temp_install_dir.exists():
                shutil.rmtree(temp_install_dir)
            temp_install_dir.mkdir(parents=True, exist_ok=True)

            self._ensure_not_cancelled(stop_event)
            shutil.copy2(source_model, temp_install_dir / "model.onnx")
            shutil.copy2(source_dir / "voices.bin", temp_install_dir / "voices.bin")
            shutil.copy2(source_dir / "tokens.txt", temp_install_dir / "tokens.txt")

            if source_data_dir is not None:
                shutil.copytree(source_data_dir, temp_install_dir / "espeak-ng-data")
            if source_dict_dir is not None:
                shutil.copytree(source_dict_dir, temp_install_dir / "dict")
            for source_lexicon in source_lexicons:
                shutil.copy2(source_lexicon, temp_install_dir / source_lexicon.name)

            write_download_metadata(
                temp_install_dir / "metadata.json",
                name="kokoro-multi-lang-v1_1",
                source_url=self._settings.model_url,
            )
            self._ensure_not_cancelled(stop_event)
            replace_directory(temp_install_dir, self._paths.root_dir)

    @staticmethod
    def _find_directory_with_model_files(root: Path) -> Path:
        candidate_directories = [
            root,
            *sorted(path for path in root.rglob("*") if path.is_dir()),
        ]
        for directory in candidate_directories:
            if not (directory / "voices.bin").is_file():
                continue
            if not (directory / "tokens.txt").is_file():
                continue
            if any(path.is_file() for path in directory.glob("*.onnx")):
                return directory
        raise FileNotFoundError("Unable to locate Kokoro model files in extracted archive")

    @staticmethod
    def _find_model_file(root: Path) -> Path:
        preferred_names = [
            "model.onnx",
            "model.int8.onnx",
        ]
        for file_name in preferred_names:
            candidate = root / file_name
            if candidate.is_file():
                return candidate

        onnx_files = sorted(root.glob("*.onnx"))
        if onnx_files:
            return onnx_files[0]

        raise FileNotFoundError("Unable to locate Kokoro ONNX model file")

    @staticmethod
    def _find_optional_directory(root: Path, directory_name: str) -> Path | None:
        direct_candidate = root / directory_name
        if direct_candidate.is_dir():
            return direct_candidate

        for path in sorted(root.rglob(directory_name)):
            if path.is_dir():
                return path
        return None

    @contextmanager
    def _acquire_download_lock(
        self,
        stop_event: threading.Event | None,
    ):
        lock_path = self._paths.root_dir.parent / ".kokoro.download.lock"
        with acquire_download_lock(
            lock_path,
            timeout_seconds=self._settings.timeout_seconds,
            timeout_message="Timed out while waiting for Kokoro model download lock",
            stop_event=stop_event,
            cancelled_error_factory=self._cancelled_error,
        ):
            yield

    @staticmethod
    def _cancelled_error() -> Exception:
        return KokoroPreparationCancelled("Kokoro model preparation was cancelled")

    @classmethod
    def _ensure_not_cancelled(
        cls,
        stop_event: threading.Event | None,
    ) -> None:
        if stop_event is not None and stop_event.is_set():
            raise cls._cancelled_error()
