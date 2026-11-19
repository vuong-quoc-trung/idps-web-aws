#!/usr/bin/env python3
"""Opt-in launcher; only execution (not import) starts Suricata. No runtime install.
Each process gets immutable startup generation in EVE host and Lua environment.
"""
import os
import secrets
import sys

PREFIX = 'ws-generation-'

def launch_spec(args):
    # No caller-controlled sensor-name or alternate YAML override via --set.
    if any(a == '--set' or a.startswith('--set=') for a in args):
        raise ValueError('Configuration overrides must be reviewed in YAML, not passed through launcher')
    generation = secrets.token_hex(16)
    env = dict(os.environ, WS_SENSOR_GENERATION=generation)
    return ['/usr/bin/suricata', *args, '--set', 'sensor-name='+PREFIX+generation], env

if __name__ == '__main__':
    command, environment = launch_spec(sys.argv[1:])
    os.execve(command[0], command, environment)
