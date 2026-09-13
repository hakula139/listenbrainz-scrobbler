ObjC.import('Foundation');

function snapshot(music) {
  if (!music.running()) {
    return { state: 'stopped' };
  }

  const state = music.playerState();
  if (state !== 'playing' && state !== 'paused') {
    return { state };
  }

  const track = music.currentTrack;
  const sample = {
    state,
    title: track.name(),
    artist: track.artist(),
    album: track.album(),
    duration: track.duration(),
    position: music.playerPosition(),
  };

  if (music.currentTrack.name() !== sample.title) {
    return { state: 'unavailable' };
  }

  return sample;
}

function run() {
  const music = Application('com.apple.Music');
  const output = $.NSFileHandle.fileHandleWithStandardOutput;
  while (true) {
    let result;
    try {
      result = snapshot(music);
    } catch (error) {
      result = {
        error: String(error).includes('-1743')
          ? 'Music Automation access denied (-1743)'
          : 'Music scripting query failed',
      };
    }

    const line = $(JSON.stringify(result) + '\n');
    output.writeData(line.dataUsingEncoding($.NSUTF8StringEncoding));
    delay(2);
  }
}
