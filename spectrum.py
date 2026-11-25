#!/usr/bin/env python3
"""Monitor just the selected playback sink and stream its spectrum as JSON.

Audio stays in an anonymous pipe from pw-record to the analyzer; no audio file
is created. The GUI starts this worker only when it needs the meter.
"""
import json
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
TARGET_NAME = re.compile(r'(?:alsa_output|bluez_output)\.[A-Za-z0-9_.:@+\-]{1,512}\Z')


def capture_command(target):
    if not isinstance(target,str) or not TARGET_NAME.fullmatch(target):
        raise ValueError('Saída de áudio inválida.')
    properties = {
        'stream.capture.sink': True,
        'node.dont-fallback': True,
        'node.dont-reconnect': True,
        'stream.dont-remix': True,
        'node.name': 'oab_spectrum_monitor',
        'application.name': 'Open Audio Bridge spectrum',
        'node.passive': True,
    }
    # No automatic target, microphone fallback or communication role. The
    # target is a distinct argument, not part of a shell or interpolated JSON.
    return ['pw-record','--target',target,'-P',json.dumps(properties),
            '--media-role','Music','--latency','20ms','--rate','48000',
            '--channels','2','--format','f32','--raw','-']


def target_available(target):
    try:
        capture_command(target)
        reply=subprocess.run(['pactl','-f','json','list','sinks'],
                             capture_output=True,text=True,timeout=3,check=False)
        if reply.returncode:
            return False
        sinks=json.loads(reply.stdout)
        return isinstance(sinks,list) and any(isinstance(s,dict) and s.get('name')==target for s in sinks)
    except (OSError,ValueError,subprocess.SubprocessError):
        return False


def reap(children):
    # Terminate both before waiting for either (one may be blocked on its pipe).
    for child in children:
        if child is not None and child.poll() is None:
            try:child.terminate()
            except OSError:pass
    for child in children:
        if child is None:continue
        try:
            child.wait(timeout=.5)
        except subprocess.TimeoutExpired:
            try:child.kill()
            except OSError:pass
            child.wait()
        except OSError:
            pass


def run_worker(target, stopped):
    recorder=analyzer=None
    raw_pipe=None
    try:
        args=capture_command(target)
        if stopped() or not target_available(target) or stopped():
            return 1
        recorder=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL)
        raw_pipe=recorder.stdout
        analyzer=subprocess.Popen([str(ROOT/'lib/oab_spectrum')],stdin=raw_pipe,
                                  stderr=subprocess.DEVNULL)
        # Only the analyzer should retain a read end of the PCM pipe.
        raw_pipe.close()
        raw_pipe=None
        while not stopped():
            if recorder.poll() is not None or analyzer.poll() is not None:
                break
            time.sleep(.04)
        return 0
    except (OSError,ValueError,subprocess.SubprocessError):
        # The meter is optional and must never stop or disrupt playback.
        return 1
    finally:
        if raw_pipe is not None:raw_pipe.close()
        reap((analyzer,recorder))


def main(argv=None):
    argv=sys.argv[1:] if argv is None else argv
    if len(argv)!=1:return 1
    stop=False
    def request_stop(*_args):
        # Do not raise from the signal handler during Popen: the process
        # reference must be assigned before cleanup so neither child is lost.
        nonlocal stop
        stop=True
    signal.signal(signal.SIGTERM,request_stop)
    signal.signal(signal.SIGINT,request_stop)
    return run_worker(argv[0],lambda:stop)


if __name__=='__main__':
    sys.exit(main())
