#!/usr/bin/env python
# vim:fileencoding=utf-8
# License: GPL v3 Copyright: 2016, Kovid Goyal <kovid at kovidgoyal.net>

import argparse
import tempfile
import os
import sys
import pwd
from gettext import gettext as _


from .child import Child
from .config import load_config
from .constants import appname, str_version, config_dir
from .boss import Boss
from .shaders import GL_VERSION
from .fast_data_types import glewInit, enable_automatic_opengl_error_checking
import glfw


def option_parser():
    parser = argparse.ArgumentParser(prog=appname, description=_('The {} terminal emulator').format(appname))
    a = parser.add_argument
    a('--class', default=appname, dest='cls', help=_('Set the WM_CLASS property'))
    a('--config', default=os.path.join(config_dir, 'kitty.conf'), help=_('Specify a path to the config file to use'))
    a('--cmd', '-c', default=None, help=_('Run python code in the kitty context'))
    a('-d', '--directory', default='.', help=_('Change to the specified directory when launching'))
    a('--version', action='version', version='{} {} by Kovid Goyal'.format(appname, '.'.join(str_version)))
    a('--profile', action='store_true', default=False, help=_('Show profiling data after exit'))
    a('--dump-commands', action='store_true', default=False, help=_('Output commands received from child process to stdout'))
    a('args', nargs=argparse.REMAINDER, help=_(
        'The remaining arguments are used to launch a program other than the default shell. Any further options are passed'
        ' directly to the program being invoked.'
    ))
    return parser


def setup_opengl():
    glfw.glfwWindowHint(glfw.GLFW_CONTEXT_VERSION_MAJOR, GL_VERSION[0])
    glfw.glfwWindowHint(glfw.GLFW_CONTEXT_VERSION_MINOR, GL_VERSION[1])
    glfw.glfwWindowHint(glfw.GLFW_OPENGL_PROFILE, glfw.GLFW_OPENGL_CORE_PROFILE)
    glfw.glfwWindowHint(glfw.GLFW_OPENGL_FORWARD_COMPAT, True)
    glfw.glfwWindowHint(glfw.GLFW_SAMPLES, 0)


def run_app(opts, args, child):
    setup_opengl()
    window_width = window_height = 1024
    window = glfw.glfwCreateWindow(
        window_width, window_height, args.cls.encode('utf-8'), None, None)
    if not window:
        raise SystemExit("glfwCreateWindow failed")
    glfw.glfwSetWindowTitle(window, appname.encode('utf-8'))
    try:
        glfw.glfwMakeContextCurrent(window)
        glewInit()
        glfw.glfwSwapInterval(1)
        boss = Boss(window, window_width, window_height, opts, args, child)
        glfw.glfwSetFramebufferSizeCallback(window, boss.on_window_resize)
        boss.start()
        try:
            while not glfw.glfwWindowShouldClose(window):
                boss.render()
                glfw.glfwSwapBuffers(window)
                glfw.glfwWaitEvents()
        finally:
            if boss.is_alive():
                boss.close()
                boss.join()
            boss.destroy()
    finally:
        glfw.glfwDestroyWindow(window)


def on_glfw_error(code, msg):
    if isinstance(msg, bytes):
        try:
            msg = msg.decode('utf-8')
        except Exception:
            msg = repr(msg)
    print('[glfw error]:', msg, file=sys.stderr)


def main():
    args = option_parser().parse_args()
    if args.cmd:
        exec(args.cmd)
        return
    opts = load_config(args.config)
    child = args.args or [pwd.getpwuid(os.geteuid()).pw_shell or '/bin/sh']
    child = Child(child, args.directory, opts)
    glfw.glfwSetErrorCallback(on_glfw_error)
    enable_automatic_opengl_error_checking(False)
    if not glfw.glfwInit():
        raise SystemExit('GLFW initialization failed')
    try:
        if args.profile:
            tf = tempfile.NamedTemporaryFile(prefix='kitty-profiling-stats-')
            args.profile = tf.name
            import cProfile
            import pstats
            pr = cProfile.Profile()
            pr.enable()
            run_app(opts, args, child)
            pr.disable()
            pr.create_stats()
            s = pstats.Stats(pr)
            s.add(args.profile)
            tf.close()
            s.strip_dirs()
            s.sort_stats('time', 'name')
            s.print_stats(30)
        else:
            run_app(opts, args, child)
    finally:
        glfw.glfwTerminate()
        os.closerange(3, 100)
