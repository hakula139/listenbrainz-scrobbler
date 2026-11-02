"""Count observed playback, excluding seeks and gaps between observations."""

from dataclasses import asdict, dataclass, replace
from importlib.metadata import version
from typing import Any, Self
from uuid import uuid4


SUBMISSION_CLIENT = 'listenbrainz-scrobbler'
SUBMISSION_CLIENT_VERSION = version(SUBMISSION_CLIENT)

SAMPLE_INTERVAL = 2.0
POSITION_TOLERANCE = 2.0
MAX_GAP = 10.0
LISTEN_THRESHOLD_CAP = 240.0


@dataclass(frozen=True)
class Sample:
    state: str
    title: str = ''
    artist: str = ''
    album: str = ''
    duration: float = 0
    position: float = 0

    def metadata(self) -> dict[str, Any]:
        return {
            'artist_name': self.artist,
            'track_name': self.title,
            'release_name': self.album,
            'additional_info': {
                'duration_ms': round(self.duration * 1000),
                'media_player': 'Apple Music',
                'submission_client': SUBMISSION_CLIENT,
                'submission_client_version': SUBMISSION_CLIENT_VERSION,
            },
        }

    @property
    def identity(self) -> tuple[str, str, str]:
        return self.title, self.artist, self.album


@dataclass
class Session:
    id: str
    sample: Sample
    observed_at: float
    started_at: int
    seconds: float = 0
    queued: bool = False

    def encode(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def decode(cls, data: dict[str, Any]) -> Self:
        return cls(**{**data, 'sample': Sample(**data['sample'])})

    def is_repeat(self, current: Sample, now: float) -> bool:
        elapsed = now - self.observed_at
        remaining = self.sample.duration - self.sample.position
        wrapped = remaining + current.position
        # A wrap near the end distinguishes repeats from ordinary backward seeks.
        return (
            self.sample.state == current.state == 'playing'
            and 0 < elapsed <= MAX_GAP
            and current.position < self.sample.position
            and 0 <= remaining <= MAX_GAP
            and 0 <= current.position <= MAX_GAP
            and abs(wrapped - elapsed) <= POSITION_TOLERANCE
        )

    def advance(self, current: Sample, now: float) -> None:
        elapsed = now - self.observed_at
        delta = current.position - self.sample.position
        if (
            self.sample.state == 'playing'
            and 0 < elapsed <= MAX_GAP
            and 0 <= delta <= elapsed + POSITION_TOLERANCE
        ):
            self.seconds += min(delta, elapsed)

        self.sample = current
        self.observed_at = now

    def payload(self) -> dict[str, Any]:
        return {
            'listened_at': self.started_at,
            'track_metadata': self.sample.metadata(),
        }


class Tracker:
    def __init__(self, session: Session | None = None) -> None:
        self.session = session

    def observe(self, current: Sample, now: float) -> dict[str, Any] | None:
        """Return the payload once per session when playback reaches the threshold.

        Callers must persist that payload together with the checkpoint.
        """
        if current.state == 'unavailable':
            if self.session is not None:
                self.session.sample = replace(self.session.sample, state='unavailable')
            return None

        if current.state not in ('playing', 'paused') or not (
            current.title and current.artist and current.duration > 0
        ):
            self.session = None
            return None

        if current.state == 'paused' and (
            self.session is None or self.session.sample.identity != current.identity
        ):
            self.session = None
            return None

        previous = self.session
        if (
            previous is None
            or previous.sample.identity != current.identity
            or previous.is_repeat(current, now)
        ):
            self.session = Session(
                id=uuid4().hex,
                sample=current,
                observed_at=now,
                started_at=int(now - current.position),
            )
            return None

        previous.advance(current, now)
        threshold = min(current.duration / 2, LISTEN_THRESHOLD_CAP)
        if not previous.queued and previous.seconds >= threshold:
            previous.queued = True
            return previous.payload()
        return None
