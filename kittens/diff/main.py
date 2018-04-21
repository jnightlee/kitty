#!/usr/bin/env python
# vim:fileencoding=utf-8
# License: GPL v3 Copyright: 2018, Kovid Goyal <kovid at kovidgoyal.net>

import os
import sys
from functools import partial
from gettext import gettext as _

from kitty.cli import parse_args
from kitty.key_encoding import ESCAPE

from ..tui.handler import Handler
from ..tui.loop import Loop
from ..tui.operations import clear_screen, set_line_wrapping, set_window_title
from .collect import create_collection, data_for_path
from .git import Differ
from .render import render_diff

INITIALIZING, COLLECTED, DIFFED = range(3)


def generate_diff(collection, context):
    d = Differ()

    for path, item_type, changed_path in collection:
        if item_type == 'diff':
            is_binary = isinstance(data_for_path(path), bytes)
            if not is_binary:
                d.add_diff(path, changed_path)

    return d(context)


class DiffHandler(Handler):

    def __init__(self, args, left, right):
        self.state = INITIALIZING
        self.left, self.right = left, right
        self.report_traceback_on_exit = None
        self.args = args
        self.scroll_pos = 0

    def create_collection(self):
        self.start_job('collect', create_collection, self.left, self.right)

    def generate_diff(self):
        self.start_job('diff', generate_diff, self.collection, self.args.context)

    def render_diff(self):
        self.diff_lines = tuple(render_diff(self.collection, self.diff_map, self.args, self.screen_size.cols))

    def init_terminal_state(self):
        self.write(set_line_wrapping(False))
        self.write(set_window_title('kitty +diff'))

    def initialize(self, *args):
        Handler.initialize(self, *args)
        self.init_terminal_state()
        self.draw_screen()
        self.create_collection()

    def draw_screen(self):
        if self.state < DIFFED:
            self.write(clear_screen())
            self.write(_('Calculating diff, please wait...'))
            return
        self.write(clear_screen())

    def on_key(self, key_event):
        if self.state is INITIALIZING:
            if key_event.key is ESCAPE:
                self.quit_loop(0)
            return

    def on_resize(self, screen_size):
        self.screen_size = screen_size
        if self.state > COLLECTED:
            self.render_diff()
        self.draw_screen()

    def on_job_done(self, job_id, job_result):
        if 'tb' in job_result:
            self.report_traceback_on_exit = job_result['tb']
            self.quit_loop(1)
            return
        if job_id == 'collect':
            self.collection = job_result['result']
            self.generate_diff()
        elif job_id == 'diff':
            diff_map = job_result['result']
            if isinstance(diff_map, str):
                self.report_traceback_on_exit = diff_map
                self.quit_loop(1)
                return
            self.state = DIFFED
            self.diff_map = diff_map
            self.render_diff()
            self.draw_screen()

    def on_interrupt(self):
        self.quit_loop(1)

    def on_eot(self):
        self.quit_loop(1)


OPTIONS = partial('''\
--context
type=int
default=3
Number of lines of context to show between changes.
'''.format, )


def main(args):
    msg = 'Show a side-by-side diff of the specified files/directories'
    args, items = parse_args(args[1:], OPTIONS, 'file_or_directory file_or_directory', msg, 'kitty +kitten diff')
    if len(items) != 2:
        raise SystemExit('You must specify exactly two files/directories to compare')
    left, right = items
    if os.path.isdir(left) != os.path.isdir(right):
        raise SystemExit('The items to be diffed should both be either directories or files. Comparing a directory to a file is not valid.')

    loop = Loop()
    handler = DiffHandler(args, left, right)
    loop.loop(handler)
    if loop.return_code != 0:
        if handler.report_traceback_on_exit:
            print(handler.report_traceback_on_exit, file=sys.stderr)
        raise SystemExit(loop.return_code)


def handle_result(args, current_char, target_window_id, boss):
    pass


if __name__ == '__main__':
    main(sys.argv)
