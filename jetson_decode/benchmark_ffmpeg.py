"""Measure full-process FFmpeg decode throughput, never label 1/FPS as latency."""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ffmpeg', type=Path, required=True)
    p.add_argument('--videos', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--decoders', nargs='+', default=['hevc', 'hevc_nvv4l2dec'])
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    records = []
    for video in sorted(a.videos.glob('*.mp4')):
        frames = int(video.stem.split('_')[-1])
        probe = subprocess.check_output([str(a.ffmpeg.with_name('ffprobe')), '-v', 'quiet', '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_name,width,height,nb_frames,r_frame_rate,bit_rate,has_b_frames', '-of', 'json', str(video)])
        metadata = json.loads(probe)['streams'][0]
        assert metadata['codec_name'] == 'hevc' and int(metadata['nb_frames']) == frames
        assert int(metadata['has_b_frames']) == 0
        for repeat in range(-1, 3):
            order = a.decoders if repeat % 2 else list(reversed(a.decoders))
            for decoder in order:
                tag = f'{video.stem}_{decoder}_r{repeat}'
                cmd = [str(a.ffmpeg), '-hide_banner', '-nostdin', '-nostats', '-benchmark', '-progress', 'pipe:1',
                       '-threads', '4', '-c:v', decoder, '-i', str(video), '-an', '-vsync', '0', '-f', 'null', '-']
                start = time.perf_counter()
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                wall = time.perf_counter() - start
                stdout = proc.stdout.decode(errors='replace'); stderr = proc.stderr.decode(errors='replace')
                (a.out / (tag + '.stdout.log')).write_text(stdout)
                (a.out / (tag + '.stderr.log')).write_text(stderr)
                if proc.returncode:
                    raise RuntimeError(f'{tag} failed: {stderr[-1500:]}')
                output_frames = [int(s.split('=')[1]) for s in stdout.splitlines() if s.startswith('frame=')]
                assert output_frames[-1] == frames, (tag, output_frames)
                records.append(dict(video=video.name, decoder=decoder, repeat=repeat, warmup=repeat<0,
                                    frames=frames, wall_seconds=wall, throughput_fps=frames/wall,
                                    amortized_ms_per_frame=1000*wall/frames, stream=metadata, command=cmd))
                (a.out / 'runs.json').write_text(json.dumps(records, indent=2))
                print(tag, 'OK', frames, 'frames', flush=True)
    (a.out / 'COMPLETE').write_text('All videos and explicit decoders completed\n')


if __name__ == '__main__':
    main()
