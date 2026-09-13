"""Share only fresh playback with the submission worker."""

from dataclasses import dataclass
from threading import Lock

from .tracking import MAX_GAP, Sample, Session


@dataclass(frozen=True)
class Playback:
    generation: int
    session_id: str
    sample: Sample
    observed_at: float


class PlaybackState:
    def __init__(self) -> None:
        self._lock = Lock()
        self._current: Playback | None = None
        self._generation = 0

    def update(self, session: Session | None, now: float) -> None:
        """Publish an observation using monotonic time, without retaining pauses."""
        with self._lock:
            if session is None or session.sample.state != 'playing':
                self._current = None
                return

            previous = self._current
            if (
                previous is None
                or previous.session_id != session.id
                or now - previous.observed_at > MAX_GAP
            ):
                self._generation += 1
            self._current = Playback(self._generation, session.id, session.sample, now)

    def current(self, now: float) -> Playback | None:
        with self._lock:
            current = self._current
            if current is None or now - current.observed_at > MAX_GAP:
                return None
            return current
