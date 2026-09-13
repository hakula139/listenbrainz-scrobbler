"""Count observed playback, excluding seeks and gaps between observations."""

from dataclasses import asdict, dataclass, replace
from typing import Any
from uuid import uuid4


MAX_GAP = 10.0
POSITION_TOLERANCE = 2.0


@dataclass(frozen=True)
class Sample:
    state: str
    title: str = ''
    artist: str = ''
    album: str = ''
    duration: float = 0
    position: float = 0

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
    def decode(cls, data: dict[str, Any]) -> 'Session':
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
            'track_metadata': {
                'artist_name': self.sample.artist,
                'track_name': self.sample.title,
                'release_name': self.sample.album,
                'additional_info': {
                    'duration_ms': round(self.sample.duration * 1000),
                    'media_player': 'Apple Music',
                    'submission_client': 'listenbrainz-scrobbler',
                    'submission_client_version': '0.1.0',
                },
            },
        }


class Tracker:
    def __init__(self, session: Session | None = None) -> None:
        self.session = session

    def observe(self, current: Sample, now: float) -> dict[str, Any] | None:
        if current.state == 'unavailable':
            if self.session:
                self.session.sample = replace(self.session.sample, state='unavailable')
                self.session.observed_at = now
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
        same = previous is not None and previous.sample.identity == current.identity
        repeat = previous is not None and same and previous.is_repeat(current, now)

        if previous is None or not same or repeat:
            self.session = Session(
                id=uuid4().hex,
                sample=current,
                observed_at=now,
                started_at=int(now - current.position),
            )
            return None

        previous.advance(current, now)
        if not previous.queued and previous.seconds >= min(current.duration / 2, 240):
            previous.queued = True
            return previous.payload()
        return None
