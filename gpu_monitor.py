#!/usr/bin/env python3
"""
Script to continuously check and display the state of GPU servers

This script is most useful in conjunction with an ssh-key, so a password does
not have to be entered for each SSH connection.
"""
import argparse
import logging
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import curses
from functools import partial

# Default timeout in seconds after which SSH stops trying to connect
DEFAULT_SSH_TIMEOUT = 3

# Default timeout in seconds after which remote commands are interrupted
DEFAULT_CMD_TIMEOUT = 10

# Default server file
DEFAULT_SERVER_FILE = 'servers.txt'
SERVER_FILE_PATH = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])),
                                DEFAULT_SERVER_FILE)

parser = argparse.ArgumentParser(description='Continuously check state of GPU servers')
parser.add_argument('-v', '--verbose', action='store_true', help='Be verbose')
parser.add_argument('-s', '--ssh-user', default=None, help='Username to use to connect with SSH')
parser.add_argument('--ssh-timeout', default=DEFAULT_SSH_TIMEOUT, help='Timeout in seconds after which SSH stops to connect')
parser.add_argument('--cmd-timeout', default=DEFAULT_CMD_TIMEOUT, help=('Timeout in seconds after which nvidia-smi is interrupted'))
parser.add_argument('--server-file', default=SERVER_FILE_PATH, help='File with addresses of GPU servers')
parser.add_argument('--refresh-interval', type=int, default=5, help='Refresh interval in seconds')
args = parser.parse_args()

def run_nvidiasmi_local():
    try:
        return subprocess.check_output(['nvidia-smi', '-q', '-x'], timeout=args.cmd_timeout)
    except subprocess.TimeoutExpired:
        logging.error('nvidia-smi command timed out')
        return None
    except subprocess.CalledProcessError as e:
        logging.error(f'nvidia-smi command failed: {e}')
        return None

def run_nvidiasmi_remote(server, ssh_timeout, cmd_timeout):
    try:
        return subprocess.check_output(['ssh', server, f'timeout {cmd_timeout} nvidia-smi -q -x'], timeout=ssh_timeout)
    except subprocess.TimeoutExpired:
        logging.error(f'Timeout while connecting to {server}')
        return None
    except subprocess.CalledProcessError as e:
        logging.error(f'Error running nvidia-smi on {server}: {e}')
        return None

def get_gpu_infos(nvidiasmi_output):
    gpu_infos = []
    root = ET.fromstring(nvidiasmi_output)
    for gpu in root.findall('gpu'):
        gpu_info = {
            'index': gpu.find('minor_number').text,
            'name': gpu.find('product_name').text,
            'memory_total': int(gpu.find('fb_memory_usage/total').text.split()[0]),
            'memory_used': int(gpu.find('fb_memory_usage/used').text.split()[0]),
            'memory_free': int(gpu.find('fb_memory_usage/free').text.split()[0])
        }
        gpu_infos.append(gpu_info)
    return gpu_infos

def display_gpu_infos(stdscr, server, gpu_infos, col, row_offset):
    try:
        stdscr.addstr(row_offset, col, f"Server: {server}")
    except curses.error:
        return row_offset
    row = row_offset + 1
    for gpu_info in gpu_infos:
        if row >= curses.LINES - 1:
            break
        try:
            stdscr.addstr(row, col, f"GPU {gpu_info['index']} - {gpu_info['name']}")
            row += 1
            stdscr.addstr(row, col, f"  Memory Total: {gpu_info['memory_total']} MiB")
            row += 1
            stdscr.addstr(row, col, f"  Memory Used: ", curses.color_pair(1))
            stdscr.addstr(f"{gpu_info['memory_used']} MiB", curses.color_pair(2))
            row += 1
            stdscr.addstr(row, col, f"  Memory Free: ", curses.color_pair(1))
            stdscr.addstr(f"{gpu_info['memory_free']} MiB", curses.color_pair(3))
            row += 2
        except curses.error:
            break
    if row < curses.LINES - 1:
        try:
            stdscr.addstr(row, col, "-" * (curses.COLS // 2 - 1))
        except curses.error:
            pass
    row += 2
    return row

def main(stdscr, args):
    curses.start_color()
    curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)

    if os.path.exists(args.server_file):
        with open(args.server_file) as f:
            servers = [line.strip() for line in f if line.strip()]
    else:
        logging.error(f"Server file {args.server_file} does not exist.")
        return

    while True:
        stdscr.clear()
        max_row, max_col = stdscr.getmaxyx()
        col_width = max_col // 2
        left_col_offset = 0
        right_col_offset = 0

        for i, server in enumerate(servers):
            if i % 2 == 0:
                col = 0
                row_offset = left_col_offset
                left_col_offset = display_gpu_infos(stdscr, server, get_gpu_infos(run_nvidiasmi_local() if server in ['.', 'localhost', '127.0.0.1'] else run_nvidiasmi_remote(server, args.ssh_timeout, args.cmd_timeout)), col, row_offset)
            else:
                col = col_width + 1  # Adjusted for vertical separator
                row_offset = right_col_offset
                right_col_offset = display_gpu_infos(stdscr, server, get_gpu_infos(run_nvidiasmi_local() if server in ['.', 'localhost', '127.0.0.1'] else run_nvidiasmi_remote(server, args.ssh_timeout, args.cmd_timeout)), col, row_offset)

        # Draw vertical separator
        for row in range(max_row):
            try:
                stdscr.addch(row, col_width, '|')
            except curses.error:
                pass

        stdscr.refresh()
        time.sleep(args.refresh_interval)

if __name__ == '__main__':
    curses.wrapper(main, args)
