"""Count observed playback, excluding seeks and gaps between observations."""

from dataclasses import asdict, dataclass
from uuid import uuid4


MAX_GAP = 10.0
POSITION_TOLERANCE = 2.0


@dataclass
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

    def encode(self) -> dict:
        return asdict(self)

    @classmethod
    def decode(cls, data: dict) -> 'Session':
        return cls(**{**data, 'sample': Sample(**data['sample'])})


class Tracker:
    def __init__(self, session: Session | None = None):
        self.session = session

    def observe(self, current: Sample, now: float) -> dict | None:
        if current.state == 'unavailable':
            if self.session:
                self.session.sample.state = 'unavailable'
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
        elapsed = now - previous.observed_at if previous else 0
        same = previous is not None and previous.sample.identity == current.identity
        repeat = False
        if (
            previous is not None
            and same
            and previous.sample.state == 'playing'
            and current.state == 'playing'
        ):
            remaining = previous.sample.duration - previous.sample.position
            wrapped = remaining + current.position
            # A wrap near the end distinguishes repeats from ordinary backward seeks.
            repeat = (
                0 < elapsed <= MAX_GAP
                and current.position < previous.sample.position
                and 0 <= remaining <= MAX_GAP
                and 0 <= current.position <= MAX_GAP
                and abs(wrapped - elapsed) <= POSITION_TOLERANCE
            )

        if previous is None or not same or repeat:
            self.session = Session(
                id=uuid4().hex,
                sample=current,
                observed_at=now,
                started_at=int(now - current.position),
            )
            return None

        delta = current.position - previous.sample.position
        if (
            previous.sample.state == 'playing'
            and 0 < elapsed <= MAX_GAP
            and 0 <= delta <= elapsed + POSITION_TOLERANCE
        ):
            previous.seconds += min(delta, elapsed)
        previous.sample = current
        previous.observed_at = now

        if not previous.queued and previous.seconds >= min(current.duration / 2, 240):
            previous.queued = True
            return {
                'listened_at': previous.started_at,
                'track_metadata': {
                    'artist_name': current.artist,
                    'track_name': current.title,
                    'release_name': current.album,
                    'additional_info': {
                        'duration_ms': round(current.duration * 1000),
                        'media_player': 'Apple Music',
                        'submission_client': 'listenbrainz-scrobbler',
                        'submission_client_version': '0.1.0',
                    },
                },
            }
        return None
