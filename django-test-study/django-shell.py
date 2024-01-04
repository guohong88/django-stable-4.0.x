# !/usr/bin/env python
# -*-coding:utf-8 -*-

"""
# File       : django-shell.py
# Time       ：2023/10/26 0:11
# Author     ：author luoghong
# version    ：python 3.10
# Description：
"""
import os
import sys
import traceback
import code


from django.utils.datastructures import OrderedSet


def python():  # 交互模式3

    # 1.shell 自带环境变量Set up a dictionary to serve as the environment for the shell.
    imported_objects = {}

    # We want to honor both $PYTHONSTARTUP and .pythonrc.py, so follow system
    # conventions and get $PYTHONSTARTUP first then .pythonrc.py.

    # 2 。不影响主体逻辑注释
    # if not options["no_startup"]: # 默认为true
    #     for pythonrc in OrderedSet(
    #         [os.environ.get("PYTHONSTARTUP"), os.path.expanduser("~/.pythonrc.py")]
    #     ):
    #         if not pythonrc:
    #             continue
    #         if not os.path.isfile(pythonrc):
    #             continue
    #         with open(pythonrc) as handle:
    #             pythonrc_code = handle.read()
    #         # Match the behavior of the cpython shell where an error in
    #         # PYTHONSTARTUP prints an exception and continues.
    #         try:
    #             exec(compile(pythonrc_code, pythonrc, "exec"), imported_objects)
    #         except Exception:
    #             traceback.print_exc()

    # By default, this will set up readline to do tab completion and to read and
    # write history to the .python_history file, but this can be overridden by
    # $PYTHONSTARTUP or ~/.pythonrc.py.
    try:
        hook = sys.__interactivehook__im
    except AttributeError:
        # Match the behavior of the cpython shell where a missing
        # sys.__interactivehook__ is ignored.
        pass
    else:
        try:
            hook()
        except Exception:
            # Match the behavior of the cpython shell where an error in
            # sys.__interactivehook__ prints a warning and the exception
            # and continues.
            print("Failed calling sys.__interactivehook__")
            traceback.print_exc()

    #   代码补全 Set up tab completion for objects imported by $PYTHONSTARTUP or
    # ~/.pythonrc.py.
    try:
        import readline
        import rlcompleter

        readline.set_completer(rlcompleter.Completer(imported_objects).complete)
    except ImportError:
        pass

    # 开始交互 核心代码 Start the interactive interpreter.
    imported_objects["name"] = "luoghong"
    code.interact(local=imported_objects)

if __name__ == '__main__':
    import os
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_frist.settings')
    # DJANGO_SETTINGS_MODULE=django_frist.settings
    from django.apps import apps
    # 方式一
    # from django_frist import settings
    # # settings.INSTALLED_APPS
    # apps.populate(settings.INSTALLED_APPS)
    # apps.app_ready()
    # 方式二
    django.setup()
    python()
