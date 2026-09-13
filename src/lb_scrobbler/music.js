const music = Application("com.apple.Music");
if (!music.running()) {
  JSON.stringify({ state: "stopped" });
} else {
  const state = music.playerState();
  if (state !== "playing" && state !== "paused") {
    JSON.stringify({ state: state });
  } else {
    const track = music.currentTrack;
    JSON.stringify({
      state: state,
      title: track.name(),
      artist: track.artist(),
      album: track.album(),
      duration: track.duration(),
      position: music.playerPosition(),
    });
  }
}
